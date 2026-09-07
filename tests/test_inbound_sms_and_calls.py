"""Texting and calling, exercised instead of grepped.

Two live failures paid for these tests.

INBOUND. `sms.pb.js` used to compare Twilio's signature against
ANTICIPY_TWILIO_WEBHOOK_URL byte-for-byte, and 503 when that var was unset. The
var has to be identical on two Railway services that nobody diffs — the hook
runs on PocketBase, the thing that binds the number runs on the worker
(brain/worker.py:340) — and on 2026-08-12→15 they disagreed: a stale
"?token=..." binding against a clean env URL, every inbound text 403, zero
inbound events for three days, and the only symptom on Twilio's side of the wire
(brain/worker.py:382-387). Twilio signs the exact URL it requested, so the hook
now reconstructs that URL from the request. These tests run the real hook source
in a stand-in PocketBase runtime and check the reconstruction, the refusals, and
that no refusal is silent.

CALLS. `VoiceArm.call()` would dial with a bare string: no goal, no named
callee, and no record that anyone approved it. MVP spec §06 (businesses only,
script and goal, disclosure, never a person unless explicitly asked) and §08
(Speak: always ask, script shown before dialing) are checked here as behaviour.
Nothing in this file can place a call or send a text: the rig guard refuses from
a pytest process, which is itself one of the assertions.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from brain import voice_arm as va  # noqa: E402
from brain.conversation import MockTransport, TwilioTransport  # noqa: E402

AUTH_TOKEN = "test-auth-token"
ACCOUNT = "AC" + "1" * 32
NUMBER = "+15550001111"


# --------------------------------------------------------------- inbound SMS

def approved_plan(**over):
    fields = dict(
        to="+16045550111",
        goal="hold a table for two at 7:30 tonight",
        script="I'd like to book a table for two at seven thirty tonight.",
        callee="Earls Kitchen, Yaletown",
        callee_kind="business",
        approved_by_owner=True,
    )
    fields.update(over)
    return va.CallPlan(**fields)


def test_an_unapproved_call_is_refused():
    """MVP §08: Speak is always-ask. The dial is what enforces it."""
    assert "not approved" in approved_plan(approved_by_owner=False).refusal()


def test_a_call_with_no_script_or_no_goal_is_refused():
    assert "no script" in approved_plan(script="").refusal()
    assert "no goal" in approved_plan(goal="").refusal()


def test_calling_a_person_needs_that_exact_call_to_have_been_asked_for():
    """MVP §06: businesses only, unless he asked for this one call."""
    person = approved_plan(callee_kind="person", callee="Mum")
    assert "BUSINESSES only" in person.refusal()
    assert person.refusal(), "a person is refused by default"
    asked = approved_plan(callee_kind="person", callee="Mum",
                          explicitly_requested=True)
    assert asked.refusal() == ""


def test_a_business_call_with_a_script_a_goal_and_an_ok_is_allowed():
    assert approved_plan().refusal() == ""


def test_every_call_discloses_itself_before_it_says_anything_else():
    """MVP §06 disclosure, and it cannot be edited out by the script writer."""
    plan = approved_plan(script="Do you have a table at seven thirty?")
    spoken = plan.spoken()
    assert spoken.startswith("Hi — this is an automated assistant")
    assert "may be recorded" in spoken
    assert spoken.index("automated assistant") < spoken.index("table")
    assert plan.spoken() in va.twiml_for(plan)


def test_the_approval_card_shows_the_number_the_goal_and_the_words():
    card = approved_plan().approval_card()
    for expected in ("+16045550111", "Earls Kitchen, Yaletown",
                     "hold a table for two", "automated assistant",
                     "seven thirty tonight"):
        assert expected in card, expected


def test_a_bare_string_call_is_refused_instead_of_dialed():
    """brain/anticipy_core.py:2151 still holds `call(owner_phone, message)`.

    A string carries no goal, no callee and no approval, so it is exactly the
    call that must not happen — and it must not happen loudly.
    """
    arm = _arm()
    lines = []
    arm.journal = lines.append
    with pytest.raises(va.CallRefused):
        arm.call("+16045550111", "your dentist called")
    assert any("REFUSED an unscripted call" in line for line in lines)


def test_a_malformed_number_or_voice_name_never_reaches_twilio():
    assert "E.164" in approved_plan(to="6045550111").refusal()
    with pytest.raises(va.CallRefused):
        va.twiml_for(approved_plan(), voice='Joanna"/><Dial>+15551234567</Dial>')


# ------------------------------------------------- rigs never reach a person

def _arm(**env):
    """A VoiceArm with credentials present, as an inherited shell export has."""
    # An inherited API key would decide which credential these tests exercise,
    # so the auth-token lane is pinned by REMOVING the pair the arm prefers.
    for key in va.API_KEY_ENV:
        os.environ.pop(key, None)
    for key, value in {"TWILIO_ACCOUNT_SID": ACCOUNT,
                       "TWILIO_AUTH_TOKEN": AUTH_TOKEN,
                       "TWILIO_PHONE_NUMBER": NUMBER, **env}.items():
        os.environ[key] = value
    return va.VoiceArm()


def test_missing_credentials_are_a_clean_failure_naming_every_missing_variable(monkeypatch):
    for name in va.REQUIRED_ENV + va.API_KEY_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", ACCOUNT)
    with pytest.raises(va.VoiceNotConfigured) as caught:
        va.VoiceArm()
    message = str(caught.value)
    assert "TWILIO_AUTH_TOKEN" in message and "TWILIO_PHONE_NUMBER" in message
    assert "TWILIO_ACCOUNT_SID" not in message, "only the missing ones"


def test_a_test_process_holding_real_credentials_cannot_text_or_call(monkeypatch):
    """The guarantee the local rig currently gets by convention.

    proof/local_rig.sh unsets TWILIO_* so a laptop worker cannot text a real
    person. An inherited shell export defeats a convention; this does not.
    """
    monkeypatch.setattr(va.requests, "post", _explode)
    arm = _arm()
    lines = []
    arm.journal = lines.append
    with pytest.raises(va.SendFailed):
        arm.text("+16045550111", "hi")
    with pytest.raises(va.SendFailed):
        arm.call(approved_plan())
    assert all("pytest" in line for line in lines if "REFUSED" in line), lines
    assert len([line for line in lines if "REFUSED" in line]) == 2


def test_a_local_backend_is_a_rig_even_outside_pytest(monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    # Swap the module's view of `sys` rather than emptying the real
    # sys.modules, which would take the import machinery down with it.
    monkeypatch.setattr(va, "sys", types.SimpleNamespace(modules={}))
    for local in ("http://127.0.0.1:8090", "http://localhost:8090",
                  "https://mac-mini.local"):
        monkeypatch.setenv("ANTICIPY_PB", local)
        assert va._rig_reason(), local
    monkeypatch.setenv("ANTICIPY_PB", "https://api.anticipy.ai")
    assert va._rig_reason() == ""
    monkeypatch.delenv("ANTICIPY_PB")
    assert va._rig_reason(), "an unset backend URL is loopback (brain/worker.py:38)"


def _explode(*_a, **_kw):
    raise AssertionError("the rig guard let a request through to Twilio")


class _Response:
    def __init__(self, payload, status=201):
        self._payload = payload
        self.status_code = status
        self.ok = status < 400
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


def _live(monkeypatch, payload, status=201):
    """A VoiceArm that believes it is the deployed worker, with Twilio faked."""
    sent = {}
    monkeypatch.setattr(va, "_rig_reason", lambda: "")

    def fake_post(url, **kw):
        sent["url"] = url
        sent["data"] = kw.get("data")
        return _Response(payload, status)

    monkeypatch.setattr(va.requests, "post", fake_post)
    return _arm(), sent


def test_a_twilio_failure_is_never_returned_as_a_sent_message(monkeypatch):
    """A 201 whose status is "failed" is a failed send wearing a success code."""
    arm, _ = _live(monkeypatch, {"sid": "SM1", "status": "failed",
                                 "error_code": 21610,
                                 "error_message": "unsubscribed recipient"})
    with pytest.raises(va.SendFailed) as caught:
        arm.text("+16045550111", "hi")
    assert "21610" in str(caught.value)


def test_an_http_error_from_twilio_is_a_failure_with_the_reason(monkeypatch):
    arm, _ = _live(monkeypatch, {"code": 21606, "message": "not a valid sender"},
                   status=400)
    with pytest.raises(va.SendFailed) as caught:
        arm.text("+16045550111", "hi")
    assert "21606" in str(caught.value)


def test_a_body_with_no_sid_is_a_failure(monkeypatch):
    arm, _ = _live(monkeypatch, {"status": "queued"})
    with pytest.raises(va.SendFailed):
        arm.text("+16045550111", "hi")


def test_a_good_send_reports_the_sid_and_does_not_claim_delivery(monkeypatch):
    """Twilio answers a create call with "queued": it has the message, and no
    handset has seen it. `delivered` is the field that says which of those two
    things happened, and it is False here."""
    arm, sent = _live(monkeypatch, {"sid": "SM7", "status": "queued"})
    assert arm.text("+16045550111", "hi") == {
        "sid": "SM7", "status": "queued", "delivered": False}
    assert sent["data"]["To"] == "+16045550111"


def test_an_approved_call_dials_with_the_disclosure_and_records_the_goal(monkeypatch):
    arm, sent = _live(monkeypatch, {"sid": "CA9", "status": "queued"})
    lines = []
    arm.journal = lines.append
    out = arm.call(approved_plan())
    assert out["sid"] == "CA9"
    assert out["goal"] == "hold a table for two at 7:30 tonight"
    assert sent["url"].endswith("/Calls.json")
    assert "automated assistant" in sent["data"]["Twiml"]
    # §06's "drops the transcript in the feed": the script, the goal and the
    # callee are journalled before the dial, so a crash mid-call still leaves
    # the record of what was attempted.
    assert any("CALLING Earls Kitchen, Yaletown" in line and "goal:" in line
               for line in lines), lines


# --------------------------------------------------------------- transports

def test_the_default_transport_cannot_reach_anyone():
    assert MockTransport().send("+16045550111", "hi")["mock"] is True


def test_a_live_transport_without_an_arm_is_refused_at_construction():
    with pytest.raises(ValueError):
        TwilioTransport(None)


def test_a_live_transport_hands_failures_straight_through(monkeypatch):
    """`say()` returns whatever the transport returns, so a swallowed failure
    here becomes a message the feed claims was delivered."""
    class Boom:
        def text(self, to, body):
            raise va.SendFailed("Twilio said no")

    with pytest.raises(va.SendFailed):
        TwilioTransport(Boom()).send("+16045550111", "hi")
