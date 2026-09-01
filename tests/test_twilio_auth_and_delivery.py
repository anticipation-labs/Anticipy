"""Which credential goes out, and what a send is allowed to claim.

Three things are being defended here, all of them things that have already gone
wrong once in this product:

1. THE CREDENTIAL. Everything authenticated with TWILIO_AUTH_TOKEN, which
   grants full account access — Twilio's own console says so. Outbound now
   prefers a scoped, revocable API key. Inbound CANNOT: Twilio signs webhooks
   with the account auth token and offers no API-key equivalent, so
   backend/pb_hooks/sms.pb.js must keep reading it forever. The two halves use
   different credentials on purpose, and the pull to "finish" the migration by
   deleting the auth token is exactly what would make every text he sends 503.

2. WHAT A SEND MAY CLAIM. A 201 whose status is "queued" means Twilio took the
   request; it does not mean a handset saw it. A record that says otherwise is
   how "she stamped them delivered and sent nothing for ten hours" happened.

3. THE ONE WEBHOOK URL. ANTICIPY_TWILIO_WEBHOOK_URL had to be identical on two
   Railway services nobody diffs; on 2026-08-12→15 they disagreed and every
   inbound text 403ed for three days. The worker derives the value from
   ANTICIPY_PB — the address it already uses to reach the database — and
   refuses rather than guessing when a pin contradicts it.

No test here sends anything. The end-to-end recorded-request proof runs as a
subprocess at the bottom (proof/twilio_outbound_proof.py).
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import types

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from brain import voice_arm as va          # noqa: E402
import brain.worker as worker              # noqa: E402
from brain.conversation import MockTransport, TwilioTransport  # noqa: E402

ACCOUNT = "AC" + "1" * 32
KEY_SID = "SK" + "2" * 32
KEY_SECRET = "key-secret-value"
AUTH_TOKEN = "account-auth-token-value"
NUMBER = "+15550001111"

TWILIO_NAMES = ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_PHONE_NUMBER",
                "TWILIO_FROM", "TWILIO_API_KEY_SID", "TWILIO_API_KEY_SECRET",
                "TWILIO_API_BASE", "TWILIO_MOCK",
                "ANTICIPY_TWILIO_WEBHOOK_URL")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """No inherited Twilio variable may decide the outcome of a test.

    The whole reason this file exists is that a shell export outlives the
    terminal it was typed in; a test suite that reads the ambient environment
    would pass or fail depending on whose laptop it ran on.
    """
    for name in TWILIO_NAMES:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def env(**over):
    values = {"TWILIO_ACCOUNT_SID": ACCOUNT, "TWILIO_AUTH_TOKEN": AUTH_TOKEN,
              "TWILIO_PHONE_NUMBER": NUMBER}
    values.update(over)
    return {k: v for k, v in values.items() if v is not None}


# ------------------------------------------------------------- the credential

def test_an_api_key_is_preferred_over_the_full_access_auth_token():
    cred = va.rest_credential(env(TWILIO_API_KEY_SID=KEY_SID,
                                  TWILIO_API_KEY_SECRET=KEY_SECRET))
    assert cred.basic() == (KEY_SID, KEY_SECRET)
    assert cred.describes == f"API key {KEY_SID}"
    assert not cred.complaint


def test_the_auth_token_is_the_fallback_so_nothing_breaks_before_a_key_exists():
    cred = va.rest_credential(env())
    assert cred.basic() == (ACCOUNT, AUTH_TOKEN)
    assert "full-account" in cred.describes, "say what it costs, every time"


def test_a_half_configured_key_falls_back_and_says_which_half_is_missing():
    """A typo in one variable must not stop her texting, and must not quietly
    promote the full-access token behind anyone's back."""
    cred = va.rest_credential(env(TWILIO_API_KEY_SID=KEY_SID))
    assert cred.basic() == (ACCOUNT, AUTH_TOKEN)
    assert "TWILIO_API_KEY_SECRET" in cred.complaint
    other = va.rest_credential(env(TWILIO_API_KEY_SECRET=KEY_SECRET))
    assert "TWILIO_API_KEY_SID" in other.complaint


def test_no_credential_at_all_names_both_ways_to_fix_it():
    cred = va.rest_credential(env(TWILIO_AUTH_TOKEN=None))
    assert not cred
    for expected in ("TWILIO_API_KEY_SID", "TWILIO_API_KEY_SECRET",
                     "TWILIO_AUTH_TOKEN"):
        assert expected in cred.complaint, cred.complaint


def test_a_key_secret_never_appears_in_anything_loggable():
    cred = va.rest_credential(env(TWILIO_API_KEY_SID=KEY_SID,
                                  TWILIO_API_KEY_SECRET=KEY_SECRET))
    assert KEY_SECRET not in cred.describes + cred.complaint


def test_the_arm_authenticates_with_the_key_and_keeps_the_account_in_the_path(clean_env):
    for name, value in env(TWILIO_API_KEY_SID=KEY_SID,
                           TWILIO_API_KEY_SECRET=KEY_SECRET).items():
        clean_env.setenv(name, value)
    arm = va.VoiceArm(journal=lambda _line: None)
    assert arm.auth == (KEY_SID, KEY_SECRET)
    # An API key authenticates AS the account; it does not replace it.
    assert arm.base.endswith(f"/2010-04-01/Accounts/{ACCOUNT}")


def test_a_half_configured_key_complains_on_the_journal_at_construction(clean_env):
    for name, value in env(TWILIO_API_KEY_SID=KEY_SID).items():
        clean_env.setenv(name, value)
    lines = []
    va.VoiceArm(journal=lines.append)
    assert any("TWILIO_API_KEY_SECRET" in line for line in lines), lines


def test_the_missing_credential_message_names_a_credential_not_one_variable(clean_env):
    clean_env.setenv("TWILIO_ACCOUNT_SID", ACCOUNT)
    with pytest.raises(va.VoiceNotConfigured) as caught:
        va.VoiceArm()
    message = str(caught.value)
    assert "TWILIO_PHONE_NUMBER" in message
    assert "TWILIO_API_KEY_SID" in message and "TWILIO_AUTH_TOKEN" in message


def test_inbound_signature_validation_still_reads_the_account_auth_token():
    """The subtlety that would otherwise be "finished" by deleting a variable.

    Twilio computes X-Twilio-Signature with the ACCOUNT AUTH TOKEN. There is no
    API-key equivalent, so the hook cannot migrate with the outbound path, and
    both files have to say so where the next person will read it.
    """
    hook = (ROOT / "backend" / "pb_hooks" / "sms.pb.js").read_text()
    assert 'const authToken = $os.getenv("TWILIO_AUTH_TOKEN")' in hook
    assert "TWILIO_API_KEY_SECRET" in hook, "warn where the mistake is made"
    assert "API key cannot stand in for it" in hook
    arm_source = (ROOT / "brain" / "voice_arm.py").read_text()
    assert "API-key equivalent" in arm_source


def test_the_arm_never_authenticates_a_send_with_a_hardcoded_pair():
    """auth=(self.sid, self.token) was the old shape, in two places. Neither
    may come back: `self.token` no longer exists, and a request that rebuilt it
    would silently keep using the full-access token after a key was minted."""
    source = (ROOT / "brain" / "voice_arm.py").read_text()
    assert "self.token" not in source
    assert source.count("auth=self.auth") == 2, "Messages.json and Calls.json"


# ------------------------------------------------------- what a send may claim

class _Response:
    def __init__(self, payload, status=201):
        self._payload = payload
        self.status_code = status
        self.ok = status < 400
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


def _arm(clean_env, payload, status=201, **over):
    """A VoiceArm that believes it is deployed, with Twilio's wire recorded."""
    for name, value in env(**over).items():
        clean_env.setenv(name, value)
    clean_env.setattr(va, "_rig_reason", lambda: "")
    sent = {}

    def fake_post(url, **kw):
        sent["url"] = url
        sent["auth"] = kw.get("auth")
        sent["data"] = kw.get("data")
        return _Response(payload, status)

    clean_env.setattr(va.requests, "post", fake_post)
    return va.VoiceArm(journal=lambda _line: None), sent


def test_a_queued_message_is_accepted_by_twilio_and_not_called_delivered(clean_env):
    arm, _ = _arm(clean_env, {"sid": "SM7", "status": "queued"})
    out = arm.text("+16045550111", "hi")
    assert out["status"] == "queued"
    assert out["delivered"] is False, "queued means Twilio has it, not that he does"


def test_only_a_status_that_means_a_handset_saw_it_reads_as_delivered(clean_env):
    for status, delivered in (("queued", False), ("accepted", False),
                              ("sending", False), ("sent", True),
                              ("delivered", True)):
        arm, _ = _arm(clean_env, {"sid": "SM7", "status": status})
        assert arm.text("+16045550111", "hi")["delivered"] is delivered, status


def test_undelivered_and_failed_are_failures_not_pending_deliveries(clean_env):
    for status in ("failed", "undelivered", "canceled"):
        arm, _ = _arm(clean_env, {"sid": "SM7", "status": status})
        with pytest.raises(va.SendFailed) as caught:
            arm.text("+16045550111", "hi")
        assert status in str(caught.value)


def test_every_4xx_and_5xx_from_twilio_raises_rather_than_returning(clean_env):
    for status in (400, 401, 403, 429, 500, 503):
        arm, _ = _arm(clean_env, {"code": 20003, "message": "authenticate"},
                      status=status)
        with pytest.raises(va.SendFailed) as caught:
            arm.text("+16045550111", "hi")
        assert str(status) in str(caught.value), status


def test_a_401_from_a_revoked_api_key_is_loud_about_the_credential(clean_env):
    """The exact shape of the trap in .env.local: a rotated SK pair 401s with
    code 20003, and preferring it silently would have cost her voice."""
    arm, sent = _arm(clean_env, {"code": 20003, "message": "Authenticate"},
                     status=401, TWILIO_API_KEY_SID=KEY_SID,
                     TWILIO_API_KEY_SECRET=KEY_SECRET)
    with pytest.raises(va.SendFailed) as caught:
        arm.text("+16045550111", "hi")
    assert "20003" in str(caught.value)
    assert sent["auth"] == (KEY_SID, KEY_SECRET), "it really did use the key"


def test_the_mock_transport_record_does_not_read_as_a_delivery():
    rec = MockTransport().send("+16045550111", "hi")
    assert rec["mock"] is True and rec["delivered"] is False


def test_a_live_transport_lets_every_failure_through_untouched():
    class Boom:
        def text(self, to, body):
            raise va.SendFailed("Twilio said no")

    with pytest.raises(va.SendFailed):
        TwilioTransport(Boom()).send("+16045550111", "hi")


class _Boom:
    def text(self, to, body):
        raise va.SendFailed("Twilio refused the text: HTTP 429 too many requests")


def _convo(transport):
    """A Conversation with no owner identity, so nothing reaches the backend:
    `_owner_filter()` returns "" and the thread rebuild short-circuits."""
    from brain.conversation import Conversation
    anticipy = types.SimpleNamespace(llm=None, owner_ref="", owner_id="")
    return Conversation(anticipy, transport=transport)


def test_a_failed_text_comes_out_of_say_as_a_failure_not_a_record():
    """This is the seam that decides whether the feed lies.

    `notify_owner` wraps `say()` in a try/except and returns None on an
    exception; every caller reads that None as "he was NOT told" and leaves the
    card standing (brain/anticipy_core.py:1557, worker.py:250/736/1159). So the
    one thing say() owes is to not turn a failure into a return value.
    """
    convo = _convo(TwilioTransport(_Boom()))
    with pytest.raises(va.SendFailed) as caught:
        convo.say("+16045550111", "your table is held")
    assert "429" in str(caught.value)


def test_a_mock_conversation_records_the_text_without_claiming_delivery():
    transport = MockTransport()
    out = _convo(transport).say("+16045550111", "your table is held")
    assert out["delivered"] is False and out["mock"] is True
    assert [(r["to"], r["body"]) for r in transport.sent] == \
        [("+16045550111", "your table is held")]


def test_twilio_mock_is_read_instead_of_being_a_switch_that_does_nothing(clean_env):
    """It sits in .env.local and silenced two services — and NOTHING read it.
    A muzzle nobody honours is worse than no muzzle: it is a false belief."""
    for name, value in env(TWILIO_MOCK="true").items():
        clean_env.setenv(name, value)
    assert va.muzzled() is True
    assert va.has_credentials() is False, "a muzzled worker uses MockTransport"
    clean_env.setattr(va, "requests",
                      type("X", (), {"post": staticmethod(
                          lambda *a, **k: pytest.fail("a muzzled process sent"))}))
    arm = va.VoiceArm(journal=lambda _line: None)
    with pytest.raises(va.SendFailed) as caught:
        arm.text("+16045550111", "hi")
    assert "TWILIO_MOCK" in str(caught.value)


def test_twilio_mock_false_is_not_a_muzzle(clean_env):
    """The value in .env.local today is "false". Reading it as truthy would
    silence production."""
    for name, value in env(TWILIO_MOCK="false").items():
        clean_env.setenv(name, value)
    assert va.muzzled() is False and va.has_credentials() is True


def test_credentials_can_be_a_key_pair_alone_with_no_auth_token(clean_env):
    """What the worker's live/mock gate has to accept once the owner has moved
    outbound to a key and taken the token off the WORKER service (it stays on
    PocketBase, which needs it for signatures)."""
    for name, value in env(TWILIO_AUTH_TOKEN=None, TWILIO_API_KEY_SID=KEY_SID,
                           TWILIO_API_KEY_SECRET=KEY_SECRET).items():
        clean_env.setenv(name, value)
    assert va.has_credentials() is True
    assert va.VoiceArm(journal=lambda _l: None).auth == (KEY_SID, KEY_SECRET)


# --------------------------------------------------------- the one webhook URL

class _Twilio:
    """Stands in for `requests` in the worker: records reads, writes and probes."""

    def __init__(self, current="https://real.example.com/sms/inbound",
                 health_ok=True, list_ok=True):
        self.current = current
        self.health_ok = health_ok
        self.list_ok = list_ok
        self.numbers_auth = None
        self.health_urls: list[str] = []
        self.posts: list[dict] = []
        self.post_auth = None

    def get(self, url, **kw):
        if "/api/health" in url:
            self.health_urls.append(url)
            return _Response({"code": 200}, 200 if self.health_ok else 404)
        self.numbers_auth = kw.get("auth")
        if not self.list_ok:
            return _Response({}, 401)
        return _Response({"incoming_phone_numbers": [
            {"phone_number": NUMBER, "sid": "PN1", "sms_url": self.current,
             "sms_application_sid": ""}]})

    def post(self, url, **kw):
        self.posts.append(kw.get("data") or {})
        self.post_auth = kw.get("auth")
        return _Response({})


def _run(clean_env, *, pb="https://backend.example.com", pinned=None,
         current="https://real.example.com/sms/inbound", health_ok=True,
         list_ok=True, **over):
    rec = _Twilio(current=current, health_ok=health_ok, list_ok=list_ok)
    clean_env.setattr(worker, "requests", rec)
    clean_env.setattr(worker, "PB", pb)
    for name, value in env(**over).items():
        clean_env.setenv(name, value)
    if pinned is not None:
        clean_env.setenv("ANTICIPY_TWILIO_WEBHOOK_URL", pinned)
    printed: list[str] = []
    clean_env.setattr("builtins.print", lambda *a, **k: printed.append(" ".join(map(str, a))))
    worker.ensure_inbound_webhook()
    return rec, printed


def test_the_target_is_derived_from_the_address_the_worker_already_uses(clean_env):
    clean_env.setattr(worker, "PB", "https://backend.example.com")
    assert worker.webhook_target() == ("https://backend.example.com/sms/inbound", "")


def test_a_pin_is_honoured_when_derivation_cannot_work(clean_env):
    """The one case derivation cannot cover: the worker reaches PocketBase on an
    address Twilio cannot (a private network, a container name)."""
    clean_env.setattr(worker, "PB", "http://pocketbase.internal:8090")
    clean_env.setenv("ANTICIPY_TWILIO_WEBHOOK_URL",
                     "https://public.example.com/sms/inbound")
    assert worker.webhook_target()[0] == "https://public.example.com/sms/inbound"


def test_two_services_disagreeing_is_refused_and_both_values_are_named(clean_env):
    """The three-day outage, as a refusal instead of a coin flip."""
    clean_env.setattr(worker, "PB", "https://backend.example.com")
    clean_env.setenv("ANTICIPY_TWILIO_WEBHOOK_URL",
                     "https://old-backend.example.com/sms/inbound")
    url, why = worker.webhook_target()
    assert url == "", "guessing is what broke it"
    assert "old-backend.example.com" in why and "backend.example.com" in why
    assert "DISAGREE" in why


def test_a_legacy_token_query_on_the_pin_is_the_same_destination(clean_env):
    """A "?token=..." pin is the same service with a secret stapled on, not a
    different one, so it must not read as a disagreement."""
    clean_env.setattr(worker, "PB", "https://backend.example.com")
    clean_env.setenv("ANTICIPY_TWILIO_WEBHOOK_URL",
                     "https://backend.example.com/sms/inbound?token=abc")
    url, why = worker.webhook_target()
    assert url == "https://backend.example.com/sms/inbound?token=abc", why


def test_an_unreachable_derived_url_refuses_and_says_which_part_is_wrong(clean_env):
    for pb, fragment in (("http://127.0.0.1:8090", "routable"),
                         ("http://public.example.com", "https")):
        clean_env.setattr(worker, "PB", pb)
        url, why = worker.webhook_target()
        assert url == "" and fragment in why, (pb, why)


def test_the_binding_is_only_written_after_the_url_answers_as_our_backend(clean_env):
    rec, printed = _run(clean_env)
    assert rec.health_urls == ["https://backend.example.com/api/health"]
    assert rec.posts and rec.posts[0]["SmsUrl"] == "https://backend.example.com/sms/inbound"
    assert any("WEBHOOK HIJACK" in line for line in printed), printed


def test_a_url_that_serves_nothing_never_replaces_a_live_binding(clean_env):
    """Reachability proves routable, not OURS. The disagreement that caused the
    outage was between two live services, and only one of them serves the hook."""
    rec, printed = _run(clean_env, health_ok=False)
    assert rec.posts == [], "a URL that 404s must not be handed to Twilio"
    joined = " ".join(printed)
    assert "NOT repointing" in joined and "real.example.com" in joined


def test_reading_and_writing_the_binding_authenticates_with_the_api_key(clean_env):
    rec, _ = _run(clean_env, TWILIO_API_KEY_SID=KEY_SID,
                  TWILIO_API_KEY_SECRET=KEY_SECRET)
    assert rec.numbers_auth == (KEY_SID, KEY_SECRET)
    assert rec.post_auth == (KEY_SID, KEY_SECRET)


def test_a_worker_with_only_a_key_can_still_check_its_own_ear(clean_env):
    """Outbound moved off the auth token; the number's configuration is just
    another REST call, so it must move too or the check dies with the token."""
    rec, _ = _run(clean_env, TWILIO_AUTH_TOKEN=None, TWILIO_API_KEY_SID=KEY_SID,
                  TWILIO_API_KEY_SECRET=KEY_SECRET)
    assert rec.numbers_auth == (KEY_SID, KEY_SECRET)
    assert len(rec.posts) == 1


def test_a_credential_that_cannot_read_the_account_says_so_instead_of_nothing(clean_env):
    """Silence made "the key has no permissions" and "the binding is fine" the
    same observation."""
    rec, printed = _run(clean_env, list_ok=False)
    assert rec.posts == []
    joined = " ".join(printed)
    assert "401" in joined and "could not read the inbound binding" in joined


def test_a_number_that_is_not_on_this_account_is_named_out_loud(clean_env):
    rec, printed = _run(clean_env, TWILIO_PHONE_NUMBER="+15559998888")
    assert rec.posts == []
    assert any("is not on this account" in line for line in printed), printed


def test_a_correct_binding_costs_one_read_and_no_probe(clean_env):
    rec, printed = _run(clean_env, current="https://backend.example.com/sms/inbound")
    assert rec.posts == [] and rec.health_urls == []


# ------------------------------------------- a failed text is not a delivered one

class _Anticipy:
    def __init__(self, ok=True):
        self.ok = ok
        self.said: list[str] = []
        self.owner_id = "t"

    def _voice(self, _ctx):
        return None

    def notify_owner(self, message, channel="sms"):
        self.said.append(message)
        return {"sid": "SM1"} if self.ok else None


def test_a_finding_whose_text_failed_is_not_recorded_as_delivered(clean_env):
    """It returned True whatever happened, so a Twilio outage, a missing owner
    number and the rig guard all read as "he has it" and the answer he asked
    for out loud was never sent again."""
    worker._SENT_RECENTLY.clear()
    a = _Anticipy(ok=False)
    printed: list[str] = []
    clean_env.setattr("builtins.print", lambda *x, **k: printed.append(" ".join(map(str, x))))
    assert worker.deliver_fyi(a, "flights to Paris", "YVR-CDG from $612",
                              overheard=False) is False
    assert a.said, "it did attempt the send"
    assert any("NOT delivered" in line for line in printed), printed


def test_a_failing_send_is_retried_but_never_on_every_two_second_sweep(clean_env):
    worker._SENT_RECENTLY.clear()
    a = _Anticipy(ok=False)
    clean_env.setattr("builtins.print", lambda *x, **k: None)
    assert worker.deliver_fyi(a, "flights to Paris", "$612", overheard=False) is False
    assert worker.deliver_fyi(a, "flights to Paris", "$612", overheard=False) is False
    assert len(a.said) == 1, "the second pass must not hammer Twilio"
    # ...and it is a BACKOFF, not a giveaway: the finding stays undelivered and
    # the next window tries again.
    worker.mark_sent("fyi-failed:flights to Paris",
                     now=0)  # age the failure past the window
    assert worker.deliver_fyi(a, "flights to Paris", "$612", overheard=False) is False
    assert len(a.said) == 2


def test_a_delivered_finding_leaves_no_backoff_behind(clean_env):
    """Only failures back off. Marking successes would silence the NEXT finding
    that happened to share a goal string."""
    worker._SENT_RECENTLY.clear()
    a = _Anticipy(ok=True)
    clean_env.setattr("builtins.print", lambda *x, **k: None)
    assert worker.deliver_fyi(a, "dinner spots", "Jeju", overheard=False) is True
    assert worker.deliver_fyi(a, "dinner spots", "Jeju", overheard=False) is True
    assert len(a.said) == 2


# ------------------------------------------------------- calling, still gated

def _plan(**over):
    fields = dict(to="+16045550111", goal="hold a table for two at 7:30 tonight",
                  script="I'd like to hold a table for two at 7:30, please.",
                  callee="Earls Kitchen, Yaletown", approved_by_owner=True)
    fields.update(over)
    return va.CallPlan(**fields)


def test_a_call_cannot_be_placed_without_the_owners_approval(clean_env):
    """Not just refused by the plan — refused by the DIAL, which is the only
    place a caller cannot skip."""
    arm, sent = _arm(clean_env, {"sid": "CA1", "status": "queued"})
    with pytest.raises(va.CallRefused) as caught:
        arm.call(_plan(approved_by_owner=False))
    assert "not approved" in str(caught.value)
    assert sent == {}, "nothing reached Twilio"


def test_calling_a_person_needs_that_exact_call_to_have_been_asked_for(clean_env):
    arm, sent = _arm(clean_env, {"sid": "CA1", "status": "queued"})
    with pytest.raises(va.CallRefused):
        arm.call(_plan(callee_kind="person", callee="his sister"))
    assert sent == {}
    arm.call(_plan(callee_kind="person", callee="his sister",
                   explicitly_requested=True))
    assert sent["url"].endswith("/Calls.json")


def test_the_script_and_the_goal_are_shown_before_the_dial(clean_env):
    """§08: "always ask, script shown before dialing". The journal line is
    written BEFORE the POST, so a crash mid-dial still leaves the record."""
    order: list[str] = []
    for name, value in env().items():
        clean_env.setenv(name, value)
    clean_env.setattr(va, "_rig_reason", lambda: "")
    clean_env.setattr(va.requests, "post",
                      lambda url, **kw: order.append("POST")
                      or _Response({"sid": "CA1", "status": "queued"}))
    arm = va.VoiceArm(journal=lambda line: order.append(line))
    arm.call(_plan())
    assert order[0].startswith("CALLING") and "POST" in order
    assert order.index("POST") > 0
    said = order[0]
    assert "hold a table for two at 7:30 tonight" in said, "the goal"
    assert "automated assistant" in said, "and the words she will actually say"


def test_the_twiml_discloses_itself_before_saying_anything_else():
    plan = _plan(on_behalf_of="Omar")
    twiml = va.twiml_for(plan)
    assert twiml.index("automated assistant") < twiml.index("hold a table")
    assert "on behalf of Omar" in twiml
    assert "may be recorded" in twiml


def test_the_disclosure_cannot_be_edited_out_by_whoever_writes_the_script():
    """A model writing the script cannot suppress it: it is prepended, not
    optional, and the approval card shows the combined sentence."""
    plan = _plan(script="Hi, no disclosure needed here.")
    assert plan.spoken().startswith("Hi — this is an automated assistant")
    assert plan.spoken() in plan.approval_card()


# ------------------------------- the OTHER outbound path: the reset code text

RESET_HARNESS = r"""
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const args = process.argv.slice(-2);
const scenario = JSON.parse(args[0]);
const HOOKS = args[1];
// Captured by ROUTE: this file registers two handlers, and taking the last one
// registered would silently exercise /auth/reset/confirm instead.
let handlerSource = null;
const logs = [];
const saved = [];
const requests = [];

// Only what PocketBase actually exposes to a hook runtime. The handler runs in
// its own isolated context for the same reason sms.pb.js's tests do it: a
// helper hoisted out of the body passes anywhere else and ReferenceErrors in
// production.
const globals = () => ({
  $os: { getenv: (name) => (scenario.env || {})[name] || "" },
  $security: {
    randomStringWithAlphabet: () => "123456",
    sha256: (value) => "sha256:" + value,
  },
  $http: {
    send: (req) => {
      requests.push(req);
      return { statusCode: scenario.twilioStatus || 201, raw: "{}" };
    },
  },
  console: { log: (...parts) => logs.push(parts.map(String).join(" ")) },
  require: require,
  __hooks: HOOKS,
  Record: function (collection) {
    this.collection = collection;
    this.data = {};
    this.set = (key, value) => { this.data[key] = value; };
  },
});

const loader = {
  ...globals(),
  routerAdd: (m, route, fn) => {
    if (route === '/auth/reset/request') handlerSource = String(fn);
  },
};
vm.createContext(loader);
vm.runInContext(fs.readFileSync(path.join(HOOKS, 'password_reset.pb.js'), 'utf8'), loader);

const isolated = globals();
vm.createContext(isolated);
const handler = vm.runInContext('(' + handlerSource + ')', isolated);

const owner = { id: 'own1', getString: (k) => (k === 'phone' ? scenario.phone : '') };
const profile = {
  getString: (k) => (k === 'phone' ? (scenario.profilePhone || '') : ''),
};
const e = {
  requestInfo: () => ({ body: { email: 'owner@example.com' } }),
  json: (status, body) => ({ status: status, body: body }),
  app: {
    findFirstRecordByFilter: (collection) => {
      if (collection === 'owners') return owner;
      throw new Error('no rows');
    },
    findRecordsByFilter: (collection) => {
      if (collection === 'owner_profile') {
        return scenario.profilePresent ? [profile] : [];
      }
      return [];
    },
    findCollectionByNameOrId: (name) => name,
    save: (record) => { saved.push(record.data); },
  },
};

let out;
try {
  out = handler(e);
} catch (err) {
  out = { status: 500, body: String(err) };
}
process.stdout.write(JSON.stringify({
  status: out.status, logs, saved, requests,
}));
"""


def request_reset(*, twilio_status=201, **over):
    account_phone = over.pop("account_phone", "+16045550111")
    profile_present = over.pop("profile_present", False)
    profile_phone = over.pop("profile_phone", "")
    scenario = {
        "env": env(**over),
        "phone": account_phone,
        "profilePresent": profile_present,
        "profilePhone": profile_phone,
        "twilioStatus": twilio_status,
    }
    proc = subprocess.run(
        ["node", "-e", RESET_HARNESS, "--", json.dumps(scenario),
         str(ROOT / "backend" / "pb_hooks")],
        capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise AssertionError(f"harness failed: {proc.stderr[-2000:]}")
    return json.loads(proc.stdout)


def basic(user: str, secret: str) -> str:
    return "Basic " + base64.b64encode(f"{user}:{secret}".encode()).decode()


def test_the_reset_code_text_prefers_the_api_key_too():
    """The second and last outbound path in the tree. A migration that moved
    only the brain would leave "outbound no longer uses the account token" true
    of one file and false of the product."""
    out = request_reset(TWILIO_API_KEY_SID=KEY_SID, TWILIO_API_KEY_SECRET=KEY_SECRET)
    assert len(out["requests"]) == 1, out["logs"]
    sent = out["requests"][0]
    assert sent["headers"]["Authorization"] == basic(KEY_SID, KEY_SECRET)
    assert f"/Accounts/{ACCOUNT}/Messages.json" in sent["url"], sent["url"]
    assert AUTH_TOKEN not in json.dumps(sent)


def test_the_reset_code_text_still_works_on_the_auth_token_alone():
    sent = request_reset()["requests"][0]
    assert sent["headers"]["Authorization"] == basic(ACCOUNT, AUTH_TOKEN)


def test_a_half_configured_key_says_so_on_the_reset_path_and_still_sends():
    out = request_reset(TWILIO_API_KEY_SID=KEY_SID)
    assert out["requests"][0]["headers"]["Authorization"] == basic(ACCOUNT, AUTH_TOKEN)
    assert any("half set" in line for line in out["logs"]), out["logs"]


def test_a_reset_code_whose_text_failed_is_never_left_live_in_the_database():
    """"Send FIRST" is the whole design: a stored code whose text never arrived
    is an account that can be reset by whoever guesses six digits, and a person
    waiting for a message that is not coming."""
    out = request_reset(twilio_status=401)
    assert out["saved"] == [], "a failed send must not leave a usable code"
    assert any("refused the send" in line for line in out["logs"]), out["logs"]


def test_a_successful_reset_send_does_record_the_code():
    """The inverse, so the check above cannot be satisfied by never saving."""
    out = request_reset()
    assert len(out["saved"]) == 1
    assert out["saved"][0]["code_hash"].startswith("sha256:")


def test_an_explicitly_empty_profile_never_resurrects_the_signup_number():
    out = request_reset(profile_present=True, profile_phone="",
                        account_phone="+16045550111")
    assert out["requests"] == []
    assert out["saved"] == []


# --------------------------------------------- the proof, run as a real program

def test_the_recorded_request_proof_runs_green_and_sends_nothing():
    """proof/twilio_outbound_proof.py is the end-to-end evidence: the real arm,
    a real HTTP round trip, a loopback recorder, and assertions on the URL, the
    Authorization header and every parameter.

    It runs as a SUBPROCESS with PYTEST_CURRENT_TEST scrubbed, because the rig
    guard refuses to send from a pytest process — and that refusal is itself one
    of the guarantees under test elsewhere in this file.
    """
    child = dict(os.environ)
    child.pop("PYTEST_CURRENT_TEST", None)
    for name in TWILIO_NAMES:
        child.pop(name, None)
    proc = subprocess.run(
        [sys.executable, str(ROOT / "proof" / "twilio_outbound_proof.py")],
        capture_output=True, text=True, timeout=120, env=child, cwd=str(ROOT))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = proc.stdout
    for expected in ("basic auth is key-sid:key-secret",
                     "the auth token is nowhere in a key-authenticated request",
                     "with no key, outbound falls back to the auth token",
                     "a queued message is NOT reported as delivered",
                     "a 400 from Twilio raises instead of returning a record",
                     "0 sent"):
        assert expected in out, out
    # And the recorder really was loopback, so "sends nothing" is a property of
    # the address, not of a promise.
    assert "127.0.0.1" in out
    assert va.TEST_ACCOUNT_SID in out, "Twilio's test account sends nothing either"


def test_the_owners_real_number_appears_in_no_test_and_no_proof():
    """His live number is what this whole file exists to protect. A test that
    names it is one refactor away from being a test that texts it.

    Assembled from parts, because a file asserting the number is absent must not
    be the file that reintroduces it.
    """
    tail = "658" + "4447"
    radioactive = ("619" + tail, "+1" + "619" + tail)
    for path in [Path(__file__), ROOT / "proof" / "twilio_outbound_proof.py"]:
        body = path.read_text()
        for digits in radioactive:
            assert digits not in body, f"{path.name} names the owner's number"
