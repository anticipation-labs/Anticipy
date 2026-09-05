"""The Sendblue arm keeps VoiceArm's contract, to the field.

brain/conversation.py's transport calls `arm.text(to, body, media)` and reads
a dict {"sid", "status", "delivered"} — or catches SendFailed. Every caller
above it (say(), notify_owner, the deliver_* paths) was written against the
Twilio arm and must not be able to tell the difference, so what is pinned
here is what reaches the wire and what comes back, never how the file is
written:

1. WHAT A SEND MAY CLAIM. Sendblue answers a create call with QUEUED: it has
   the message, no handset has seen it. `delivered` is False for that. A 200
   whose status is ERROR or DECLINED, a 401, a reply with no message_handle,
   and a reply with an error_code all RAISE — a failed text that comes back
   as a record is how "she stamped them delivered and sent nothing for ten
   hours" happened.
2. THE RIG GUARD is voice_arm._rig_reason, the same function in the same
   order: the muzzle (ANTICIPY_SMS_MOCK or TWILIO_MOCK), then this arm's OWN
   loopback exemption, then pytest, then a local backend. Loopback on the
   OTHER vendor's base exempts nothing.
3. THE WORDS ARE THE FLOOR. A picture that Sendblue would not take costs the
   picture, once, and never the sentence — and a message Sendblue HAS is
   never sent twice.
4. THE SECRET IS NEVER LOGGED. Not in the journal, not in an exception, not
   even when the vendor's error body echoes it back.

No test here sends anything: `requests.post` is a fake, and the end-to-end
recorded-request proof (proof/sendblue_outbound_proof.py) runs as a
subprocess at the bottom over a real loopback round trip.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import types

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from brain import sendblue_arm as sb                     # noqa: E402
from brain import voice_arm as va                        # noqa: E402
from brain.conversation import Conversation, MessageTransport, TwilioTransport  # noqa: E402

KEY_ID = "sbkey-" + "7" * 20 + "9876"
SECRET = "sendblue-secret-value-" + "q" * 12
FROM = "+15005550006"
US = "+15005550001"
UK = "+442079460958"
PHOTO = "https://backend.example/api/files/evidence/rec1/shot.jpg"
HANDLE = "mh_" + "2" * 24

NAMES = ("SENDBLUE_API_KEY_ID", "SENDBLUE_API_SECRET_KEY", "SENDBLUE_FROM_NUMBER",
         "SENDBLUE_API_BASE", "SENDBLUE_STATUS_CALLBACK", "ANTICIPY_SMS_MOCK",
         "TWILIO_MOCK", "TWILIO_API_BASE", "TWILIO_ACCOUNT_SID", "ANTICIPY_PB",
         "ANTICIPY_SMS_PROVIDER")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """No inherited variable may decide the outcome of a test — a shell
    export outlives the terminal it was typed in."""
    for name in NAMES:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def configure(monkeypatch, **over):
    values = {"SENDBLUE_API_KEY_ID": KEY_ID, "SENDBLUE_API_SECRET_KEY": SECRET,
              "SENDBLUE_FROM_NUMBER": FROM}
    values.update(over)
    for name, value in values.items():
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)


class _Response:
    def __init__(self, payload, status=200, text=None):
        self._payload = payload
        self.status_code = status
        self.ok = status < 400
        self.text = json.dumps(payload) if text is None else text

    def json(self):
        if self._payload is None:
            raise ValueError("no JSON")
        return self._payload


def _arm(monkeypatch, replies=None, **over):
    """A SendblueArm that believes it is deployed, with the wire recorded.

    `replies` answers the posts in order — each a (status, payload) pair —
    and the last one repeats. The rig guard is stood down the way every
    VoiceArm test stands it down, so what is exercised here is the wire.
    """
    configure(monkeypatch, **over)
    monkeypatch.setattr(va, "_rig_reason", lambda *_a, **_k: "")
    posts: list[dict] = []
    script = list(replies or [(200, {"message_handle": HANDLE, "status": "QUEUED"})])

    def fake_post(url, **kw):
        posts.append({"url": url, "headers": dict(kw.get("headers") or {}),
                      "json": dict(kw.get("json") or {}),
                      "timeout": kw.get("timeout")})
        status, payload = script[min(len(posts), len(script)) - 1]
        return _Response(payload, status)

    monkeypatch.setattr(sb.requests, "post", fake_post)
    lines: list[str] = []
    return sb.SendblueArm(journal=lines.append), posts, lines


# ------------------------------------------------------ what a send may claim

def test_a_queued_reply_carries_the_handle_and_does_not_claim_delivery(monkeypatch):
    arm, posts, _ = _arm(monkeypatch)
    out = arm.text(US, "your table is held")
    assert out == {"sid": HANDLE, "status": "queued", "delivered": False}
    sent = posts[-1]
    assert sent["url"] == "https://api.sendblue.com/api/send-message"
    assert sent["headers"] == {"sb-api-key-id": KEY_ID, "sb-api-secret-key": SECRET}
    assert sent["json"] == {"from_number": FROM, "number": US,
                            "content": "your table is held"}
    assert sent["timeout"] == 15


def test_only_a_status_that_means_a_handset_saw_it_reads_as_delivered(monkeypatch):
    for status, delivered in (("DELIVERED", True), ("READ", True), ("SENT", True),
                              ("QUEUED", False), ("PENDING", False),
                              ("ACCEPTED", False), ("REGISTERED", False)):
        arm, _, _ = _arm(monkeypatch, [(200, {"message_handle": HANDLE, "status": status})])
        out = arm.text(US, "hi")
        assert out["delivered"] is delivered, status
        assert out["status"] == status.lower()


def test_a_200_whose_status_is_error_is_a_failure_not_a_record(monkeypatch):
    arm, _, _ = _arm(monkeypatch, [(200, {"message_handle": HANDLE, "status": "ERROR",
                                          "error_code": 4001,
                                          "error_message": "not reachable"})])
    with pytest.raises(va.SendFailed) as caught:
        arm.text(US, "hi")
    assert "status=error" in str(caught.value) and "4001" in str(caught.value)
    # The STATUS alone is the failure. A reply that says ERROR and carries no
    # error_code must not slip through on the code's absence.
    arm, _, _ = _arm(monkeypatch, [(200, {"message_handle": HANDLE, "status": "ERROR"})])
    with pytest.raises(va.SendFailed) as caught:
        arm.text(US, "hi")
    assert "status=error" in str(caught.value)


def test_declined_and_the_twilio_dead_states_are_failures_too(monkeypatch):
    for status in ("DECLINED", "FAILED", "CANCELLED", "canceled", "undelivered"):
        arm, _, _ = _arm(monkeypatch, [(200, {"message_handle": HANDLE, "status": status})])
        with pytest.raises(va.SendFailed):
            arm.text(US, "hi")


def test_every_4xx_and_5xx_raises_rather_than_returning(monkeypatch):
    for status in (400, 401, 403, 404, 429, 500, 502):
        arm, _, _ = _arm(monkeypatch, [(status, {"status": "ERROR",
                                                 "error_message": "no"})])
        with pytest.raises(va.SendFailed) as caught:
            arm.text(US, "hi")
        assert str(status) in str(caught.value)


def test_a_401_names_the_key_tail_and_never_the_secret(monkeypatch):
    arm, _, lines = _arm(monkeypatch, [(401, {"status": "ERROR",
                                              "error_message": "bad key"})])
    with pytest.raises(va.SendFailed) as caught:
        arm.text(US, "hi")
    assert "…9876" in str(caught.value)
    assert SECRET not in str(caught.value)
    assert KEY_ID[-4:] == "9876"


def test_a_reply_with_no_message_handle_is_a_failure(monkeypatch):
    arm, _, _ = _arm(monkeypatch, [(200, {"status": "QUEUED"})])
    with pytest.raises(va.SendFailed):
        arm.text(US, "hi")


def test_a_reply_with_no_json_is_a_failure(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setattr(va, "_rig_reason", lambda *_a, **_k: "")
    monkeypatch.setattr(sb.requests, "post",
                        lambda *a, **k: _Response(None, 200, text="<html>oops"))
    arm = sb.SendblueArm(journal=lambda _l: None)
    with pytest.raises(va.SendFailed) as caught:
        arm.text(US, "hi")
    assert "no JSON" in str(caught.value)


def test_a_live_status_with_an_error_code_raises_and_is_never_resent(monkeypatch):
    """A 200/QUEUED carrying an error_code is a message Sendblue HAS. It is a
    failure to the caller, and it is not sent a second time even with a
    picture to drop — the retry is for sends that went nowhere."""
    arm, posts, _ = _arm(monkeypatch, [(200, {"message_handle": HANDLE, "status": "QUEUED",
                                              "error_code": 9001})])
    with pytest.raises(va.SendFailed):
        arm.text(US, "hi", media=[PHOTO])
    assert len(posts) == 1


# --------------------------------------------------------- the words are the floor

def test_a_picture_rides_as_sendblues_own_field_and_nothing_else(monkeypatch):
    arm, posts, _ = _arm(monkeypatch)
    arm.text(US, "that's booked", media=[PHOTO])
    assert posts[-1]["json"] == {"from_number": FROM, "number": US,
                                 "content": "that's booked", "media_url": PHOTO}


def test_a_text_with_no_picture_posts_no_media_key_at_all(monkeypatch):
    arm, posts, _ = _arm(monkeypatch)
    arm.text(US, "words only")
    assert "media_url" not in posts[-1]["json"]
    arm.text(US, "words only", media=[])
    assert "media_url" not in posts[-1]["json"]


def test_a_refused_picture_costs_the_picture_and_not_the_confirmation(monkeypatch):
    arm, posts, lines = _arm(monkeypatch, [
        (400, {"status": "ERROR", "error_message": "bad media"}),
        (200, {"message_handle": HANDLE, "status": "QUEUED"})])
    out = arm.text(US, "that's booked", media=[PHOTO])
    assert out["status"] == "queued"
    assert len(posts) == 2
    assert posts[0]["json"].get("media_url") == PHOTO
    assert "media_url" not in posts[1]["json"]
    assert posts[1]["json"]["content"] == "that's booked"
    assert any("without it" in line for line in lines)


def test_a_200_error_while_carrying_a_picture_is_retried_once_without_it(monkeypatch):
    """ERROR is documented as "failed to send": nothing is on its way, so the
    words may go again without the picture and cannot double-text."""
    arm, posts, _ = _arm(monkeypatch, [
        (200, {"message_handle": HANDLE, "status": "ERROR", "error_code": 4004}),
        (200, {"message_handle": HANDLE, "status": "QUEUED"})])
    out = arm.text(US, "that's booked", media=[PHOTO])
    assert out["status"] == "queued" and len(posts) == 2
    assert "media_url" not in posts[1]["json"]


def test_a_send_with_no_picture_is_never_retried(monkeypatch):
    arm, posts, _ = _arm(monkeypatch, [(400, {"status": "ERROR"})])
    with pytest.raises(va.SendFailed):
        arm.text(US, "that's booked")
    assert len(posts) == 1


def test_the_retry_is_bounded_to_one(monkeypatch):
    arm, posts, _ = _arm(monkeypatch, [(400, {"status": "ERROR"})])
    with pytest.raises(va.SendFailed):
        arm.text(US, "that's booked", media=[PHOTO])
    assert len(posts) == 2


def test_a_foreign_number_gets_the_words_and_no_picture(monkeypatch):
    arm, posts, lines = _arm(monkeypatch)
    arm.text(UK, "that's booked", media=[PHOTO])
    assert posts[-1]["json"] == {"from_number": FROM, "number": UK,
                                 "content": "that's booked"}
    assert any("no picture" in line for line in lines)


def test_more_than_one_picture_is_no_picture(monkeypatch):
    arm, posts, lines = _arm(monkeypatch)
    arm.text(US, "that's booked", media=[PHOTO, PHOTO + "2"])
    assert "media_url" not in posts[-1]["json"]
    assert any("NO PICTURE" in line for line in lines)


def test_the_status_callback_rides_only_when_configured(monkeypatch):
    arm, posts, _ = _arm(monkeypatch)
    arm.text(US, "hi")
    assert "status_callback" not in posts[-1]["json"]
    arm, posts, _ = _arm(monkeypatch,
                         SENDBLUE_STATUS_CALLBACK="https://backend.example/sms/sendblue/status")
    arm.text(US, "hi")
    assert posts[-1]["json"]["status_callback"] == "https://backend.example/sms/sendblue/status"


# ------------------------------------------------- rigs never reach a person

def _explode(*_a, **_k):
    raise AssertionError("the rig guard let a request through to Sendblue")


def test_a_test_process_holding_real_credentials_cannot_text(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setenv("ANTICIPY_PB", "https://api.anticipy.example")
    monkeypatch.setattr(sb.requests, "post", _explode)
    lines: list[str] = []
    arm = sb.SendblueArm(journal=lines.append)
    with pytest.raises(va.SendFailed) as caught:
        arm.text(US, "hi")
    assert "pytest" in str(caught.value)
    assert any("REFUSED" in line and "Sendblue credentials" in line for line in lines)


def test_a_local_backend_is_a_rig_even_outside_pytest(monkeypatch):
    configure(monkeypatch)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    # Swap the module's view of `sys` rather than emptying the real
    # sys.modules, which would take the import machinery down with it.
    monkeypatch.setattr(va, "sys", types.SimpleNamespace(modules={}))
    monkeypatch.setattr(sb.requests, "post", _explode)
    arm = sb.SendblueArm(journal=lambda _l: None)
    for local in ("http://127.0.0.1:8090", "http://localhost:8090", "https://mac-mini.local"):
        monkeypatch.setenv("ANTICIPY_PB", local)
        with pytest.raises(va.SendFailed) as caught:
            arm.text(US, "hi")
        assert "backend is local" in str(caught.value), local
    monkeypatch.delenv("ANTICIPY_PB")
    with pytest.raises(va.SendFailed):
        arm.text(US, "hi")


def test_anticipy_sms_mock_muzzles_the_arm_ahead_of_every_exemption(monkeypatch):
    """The muzzle is read FIRST: even with this arm's base on loopback, which
    would otherwise exempt the send, ANTICIPY_SMS_MOCK=1 refuses."""
    configure(monkeypatch, SENDBLUE_API_BASE="http://127.0.0.1:9", ANTICIPY_SMS_MOCK="1")
    monkeypatch.setattr(sb.requests, "post", _explode)
    arm = sb.SendblueArm(journal=lambda _l: None)
    with pytest.raises(va.SendFailed) as caught:
        arm.text(US, "hi")
    assert "ANTICIPY_SMS_MOCK" in str(caught.value)
    assert sb.has_credentials() is False, "a muzzled worker uses MockTransport"


def test_twilio_mock_muzzles_the_sendblue_arm_too(monkeypatch):
    configure(monkeypatch, TWILIO_MOCK="true")
    monkeypatch.setattr(sb.requests, "post", _explode)
    with pytest.raises(va.SendFailed) as caught:
        sb.SendblueArm(journal=lambda _l: None).text(US, "hi")
    assert "TWILIO_MOCK" in str(caught.value)


def test_anticipy_sms_mock_muzzles_the_twilio_arm_as_well(monkeypatch):
    """One switch, both arms: the provider-neutral spelling is read by the
    shared `muzzled`, so it silences Twilio exactly as TWILIO_MOCK does."""
    monkeypatch.setenv("ANTICIPY_SMS_MOCK", "yes")
    assert va.muzzled() is True and va.muzzle_flag() == "ANTICIPY_SMS_MOCK"
    monkeypatch.setenv("ANTICIPY_SMS_MOCK", "false")
    assert va.muzzled() is False


def test_the_loopback_exemption_is_per_arm(monkeypatch):
    """Pointing TWILIO_API_BASE at loopback must not exempt a Sendblue send
    whose wire still goes to api.sendblue.com — and vice versa. The proof
    mode for one vendor is not a licence for the other."""
    configure(monkeypatch, TWILIO_API_BASE="http://127.0.0.1:9")
    assert va._rig_reason(sb._cannot_reach_a_phone), \
        "Twilio's loopback exempted a Sendblue send"
    configure(monkeypatch, TWILIO_API_BASE=None, SENDBLUE_API_BASE="http://127.0.0.1:9")
    assert va._rig_reason(sb._cannot_reach_a_phone) == "", \
        "this arm's own loopback is the proof mode"
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC" + "1" * 32)
    assert va._rig_reason(), "Sendblue's loopback exempted a Twilio send"


def test_the_guard_is_voice_arms_rig_reason_and_not_a_copy(monkeypatch):
    """One function decides what a rig is. Replacing it replaces it for this
    arm too — which is the property that makes it one place to forget."""
    configure(monkeypatch)
    calls: list[tuple] = []

    def fake_rig_reason(*args, **kwargs):
        calls.append(args)
        return "stood in"

    monkeypatch.setattr(va, "_rig_reason", fake_rig_reason)
    monkeypatch.setattr(sb.requests, "post", _explode)
    with pytest.raises(va.SendFailed) as caught:
        sb.SendblueArm(journal=lambda _l: None).text(US, "hi")
    assert "stood in" in str(caught.value)
    assert calls and calls[0][0] is sb._cannot_reach_a_phone, \
        "the arm must hand its OWN loopback check to the shared guard"


# ------------------------------------------------------------- the secret

def test_the_secret_never_appears_in_any_log_line_or_error(monkeypatch):
    """Even when the vendor's error body echoes the header back."""
    arm, _, lines = _arm(monkeypatch, [(401, {"status": "ERROR",
                                              "error_message": f"unauthorized: {SECRET}"})])
    with pytest.raises(va.SendFailed) as caught:
        arm.text(US, "hi", media=[PHOTO])
    assert SECRET not in str(caught.value)
    assert all(SECRET not in line for line in lines), lines
    assert "[secret]" in str(caught.value), "the echo was scrubbed, not dropped"
    assert SECRET not in arm.credential and "…9876" in arm.credential


def test_the_secret_is_only_ever_a_header(monkeypatch):
    arm, posts, _ = _arm(monkeypatch)
    arm.text(US, "hi")
    assert SECRET not in json.dumps(posts[-1]["json"])
    assert SECRET not in posts[-1]["url"]


# ------------------------------------------------------------ configuration

def test_missing_credentials_are_a_clean_failure_naming_every_missing_variable(monkeypatch):
    monkeypatch.setenv("SENDBLUE_API_KEY_ID", KEY_ID)
    with pytest.raises(sb.SendblueNotConfigured) as caught:
        sb.SendblueArm()
    message = str(caught.value)
    assert "SENDBLUE_API_SECRET_KEY" in message and "SENDBLUE_FROM_NUMBER" in message
    assert "SENDBLUE_API_KEY_ID" not in message, "only the missing ones"


def test_a_from_number_that_is_not_e164_is_refused_at_construction(monkeypatch):
    configure(monkeypatch, SENDBLUE_FROM_NUMBER="5005550006")
    with pytest.raises(sb.SendblueNotConfigured) as caught:
        sb.SendblueArm()
    assert "E.164" in str(caught.value)


def test_has_credentials_needs_all_three_and_no_muzzle(monkeypatch):
    assert sb.has_credentials() is False
    configure(monkeypatch)
    assert sb.has_credentials() is True
    configure(monkeypatch, SENDBLUE_FROM_NUMBER=None)
    assert sb.has_credentials() is False
    configure(monkeypatch, SENDBLUE_API_SECRET_KEY=" ")
    assert sb.has_credentials() is False
    configure(monkeypatch, ANTICIPY_SMS_MOCK="1")
    assert sb.has_credentials() is False


def test_the_api_base_is_overridable_for_the_proof_only(monkeypatch):
    assert sb.api_base() == "https://api.sendblue.com"
    monkeypatch.setenv("SENDBLUE_API_BASE", "http://127.0.0.1:7/")
    assert sb.api_base() == "http://127.0.0.1:7"
    assert "127.0.0.1" in sb._cannot_reach_a_phone()
    monkeypatch.setenv("SENDBLUE_API_BASE", "https://api.sendblue.co")
    assert sb._cannot_reach_a_phone() == ""


def test_a_call_is_refused_with_a_reason_not_a_stack_trace(monkeypatch):
    configure(monkeypatch)
    lines: list[str] = []
    arm = sb.SendblueArm(journal=lines.append)
    with pytest.raises(va.CallRefused) as caught:
        arm.call("+16045550111", "your dentist called")
    assert "Twilio" in str(caught.value)
    assert any("REFUSED a call" in line for line in lines)


# ------------------------------------------------------------- the transport

def _convo(transport):
    anticipy = types.SimpleNamespace(llm=None, owner_ref="", owner_id="")
    return Conversation(anticipy, transport=transport)


def test_the_arm_works_through_the_real_transport_and_say(monkeypatch):
    arm, posts, _ = _arm(monkeypatch)
    out = _convo(MessageTransport(arm)).say(US, "your table is held", media=[PHOTO])
    assert out == {"sid": HANDLE, "status": "queued", "delivered": False}
    assert posts[-1]["json"]["media_url"] == PHOTO
    assert MessageTransport is TwilioTransport, "one class, two names"


def test_a_failed_text_comes_out_of_say_as_a_failure_not_a_record(monkeypatch):
    arm, _, _ = _arm(monkeypatch, [(200, {"message_handle": HANDLE, "status": "ERROR",
                                          "error_code": 4001})])
    with pytest.raises(va.SendFailed):
        _convo(MessageTransport(arm)).say(US, "your table is held")


# --------------------------------------------- the proof, run as a real program

def test_the_recorded_request_proof_runs_green_and_sends_nothing():
    """proof/sendblue_outbound_proof.py is the end-to-end evidence: the real
    arm, the real transport, a real HTTP round trip, a loopback recorder, and
    assertions on the path, the headers and every field.

    A SUBPROCESS with PYTEST_CURRENT_TEST scrubbed, because the rig guard
    refuses to send from a pytest process — and that refusal is itself one of
    the guarantees under test above.
    """
    child = dict(os.environ)
    child.pop("PYTEST_CURRENT_TEST", None)
    for name in NAMES:
        child.pop(name, None)
    proc = subprocess.run(
        [sys.executable, str(ROOT / "proof" / "sendblue_outbound_proof.py")],
        capture_output=True, text=True, timeout=120, env=child, cwd=str(ROOT))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = proc.stdout
    for expected in ("the message POSTs to Sendblue's send-message path",
                     "no extra fields were smuggled in",
                     "a queued message is NOT reported as delivered",
                     "a 200 whose status is ERROR raises SendFailed through say()",
                     "a 401 raises, names the key's tail, and does not name the secret",
                     "ANTICIPY_SMS_MOCK refuses the send before any request",
                     "the secret appears in no journal line and no exception text",
                     "0 sent"):
        assert expected in out, out
    assert "127.0.0.1" in out, "the recorder really was loopback"


def test_the_owners_real_number_appears_in_no_test_and_no_proof():
    tail = "658" + "4447"
    radioactive = ("619" + tail, "+1" + "619" + tail)
    for path in [Path(__file__), ROOT / "proof" / "sendblue_outbound_proof.py",
                 ROOT / "brain" / "sendblue_arm.py"]:
        body = path.read_text()
        for digits in radioactive:
            assert digits not in body, f"{path.name} names the owner's number"
