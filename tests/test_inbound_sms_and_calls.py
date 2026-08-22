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

HOOKS = ROOT / "backend" / "pb_hooks"
AUTH_TOKEN = "test-auth-token"
ACCOUNT = "AC" + "1" * 32
NUMBER = "+15550001111"


# --------------------------------------------------------------- inbound SMS

HARNESS = r"""
const fs = require('fs');
const path = require('path');
const vm = require('vm');
// `node -e` leaves no script path in argv, so the two arguments are the tail.
const args = process.argv.slice(-2);
const scenario = JSON.parse(args[0]);
const HOOKS = args[1];
// The handler is captured as SOURCE and re-evaluated in a context that holds
// only the runtime globals, because that is what PocketBase does: a registered
// handler runs in its own pooled JS runtime and cannot see the file's top-level
// scope. Executing it in the same context as the file would let a hoisted
// helper pass here and ReferenceError in production — which is exactly what a
// live PocketBase 0.30.4 did on 2026-08-19, as HTTP 400 on every inbound text.
let handlerSource = null;
const logs = [];
const saved = [];
const headers = {};
for (const key of Object.keys(scenario.headers || {})) {
  headers[key.toLowerCase()] = scenario.headers[key];
}

const globals = () => ({
  $os: { getenv: (name) => (scenario.env || {})[name] || "" },
  __hooks: HOOKS,
  require: require,
  console: { log: (...parts) => logs.push(parts.map(String).join(" ")) },
  Record: function (collection) {
    this.collection = collection;
    this.data = {};
    this.set = (key, value) => { this.data[key] = value; };
  },
});

const loader = { ...globals(), routerAdd: (m, route, fn) => { handlerSource = String(fn); } };
vm.createContext(loader);
vm.runInContext(fs.readFileSync(path.join(HOOKS, 'sms.pb.js'), 'utf8'), loader);

const isolated = globals();
vm.createContext(isolated);
const handler = vm.runInContext('(' + handlerSource + ')', isolated);

const profiles = (scenario.owner_refs || []).map((ref) => ({
  getString: () => ref,
}));

const e = {
  request: {
    method: 'POST',
    host: scenario.host || '',
    header: { get: (name) => headers[String(name).toLowerCase()] || "" },
    url: { path: scenario.path || '/sms/inbound', rawQuery: scenario.rawQuery || '' },
  },
  // PocketBase's requestInfo().body is Go's ParseForm output, so the URL query
  // is MERGED into the form. Faithful here, because that merge is what made a
  // "?token=..." binding unverifiable no matter what was configured.
  requestInfo: () => {
    const merged = { ...(scenario.body || {}) };
    for (const pair of String(scenario.rawQuery || '').split('&')) {
      if (!pair) continue;
      const [name, value] = pair.split('=');
      merged[decodeURIComponent(name)] = decodeURIComponent(value || '');
    }
    return { body: merged };
  },
  string: (status, text) => ({ status: status, text: text }),
  response: { header: () => ({ set: () => {} }) },
  app: {
    findRecordsByFilter: (collection) => {
      if (collection === 'owner_profile') return profiles;
      return [];
    },
    findFirstRecordByFilter: () => {
      if (scenario.duplicate) return { id: 'x' };
      throw new Error('no rows');
    },
    findCollectionByNameOrId: (name) => name,
    save: (record) => { saved.push(record.data); },
  },
};

let out;
try {
  out = handler(e);
} catch (err) {
  out = { status: 500, text: String(err) };
}
process.stdout.write(JSON.stringify({ status: out.status, body: out.text, logs, saved }));
"""


def twilio_signature(url: str, params: dict, token: str = AUTH_TOKEN) -> str:
    payload = url + "".join(k + str(params[k]) for k in sorted(params))
    return base64.b64encode(
        hmac.new(token.encode(), payload.encode(), hashlib.sha1).digest()).decode()


def post(body=None, *, env=None, headers=None, host="backend.example.com",
         path="/sms/inbound", raw_query="", owner_refs=("own1",), duplicate=False,
         sign_for=None, token=AUTH_TOKEN):
    """Run the real hook against one request and return status/logs/saved rows."""
    body = dict(body if body is not None else {
        "AccountSid": ACCOUNT,
        "Body": "book it",
        "From": "+16045550111",
        "MessageSid": "SM" + "a" * 32,
        "To": NUMBER,
    })
    hdrs = {"Content-Type": "application/x-www-form-urlencoded"}
    hdrs.update(headers or {})
    if sign_for is not None:
        hdrs["X-Twilio-Signature"] = twilio_signature(sign_for, body, token)
    scenario = {
        "env": {"TWILIO_AUTH_TOKEN": AUTH_TOKEN,
                "TWILIO_ACCOUNT_SID": ACCOUNT,
                "TWILIO_PHONE_NUMBER": NUMBER,
                **(env or {})},
        "headers": hdrs, "body": body, "host": host, "path": path,
        "rawQuery": raw_query, "owner_refs": list(owner_refs),
        "duplicate": duplicate,
    }
    proc = subprocess.run(
        ["node", "-e", HARNESS, "--", json.dumps(scenario), str(HOOKS)],
        capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise AssertionError(f"harness failed: {proc.stderr[-2000:]}")
    return json.loads(proc.stdout)


def test_a_signature_over_the_requested_url_is_accepted_with_no_env_url():
    """The three-day outage, made impossible.

    No ANTICIPY_TWILIO_WEBHOOK_URL anywhere — which is the production worker's
    observed state, since it binds the number to a token-less
    "{ANTICIPY_PB}/sms/inbound" — and the text still lands.
    """
    out = post(sign_for="https://backend.example.com/sms/inbound",
               headers={"X-Forwarded-Proto": "https"})
    assert out["status"] == 200, out
    assert len(out["saved"]) == 1
    assert out["saved"][0]["kind"] == "sms_reply"
    assert out["saved"][0]["owner_ref"] == "own1"


def test_a_query_bearing_binding_validates_against_the_body_alone():
    """The exact shape that broke: Twilio's URL carried "?token=...".

    Two bugs met here. The URL had to be configured identically on two
    services, and PocketBase merged "token" into the form params so Twilio's
    signature — computed over the POST body only — could not match no matter
    what was configured. Both are gone: the URL comes off the request and the
    query keys come back out of the signed set. `sign_for` below signs exactly
    what Twilio signs, and nothing is configured.
    """
    out = post(sign_for="https://backend.example.com/sms/inbound?token=abc123",
               raw_query="token=abc123", headers={"X-Forwarded-Proto": "https"})
    assert out["status"] == 200, out
    assert len(out["saved"]) == 1
    assert "abc123" not in json.dumps(out["logs"]), "a URL secret must not be logged"


def test_a_signature_that_treats_the_query_as_a_form_field_is_refused():
    """The inverse, so the strip cannot be "fixed" by signing the query in."""
    body = {"AccountSid": ACCOUNT, "Body": "hi", "From": "+16045550111",
            "MessageSid": "SM" + "a" * 32, "To": NUMBER}
    url = "https://backend.example.com/sms/inbound?token=abc123"
    wrong = twilio_signature(url, {**body, "token": "abc123"})
    out = post(body, raw_query="token=abc123",
               headers={"X-Forwarded-Proto": "https", "X-Twilio-Signature": wrong})
    assert out["status"] == 403
    assert not out["saved"]


def test_the_proxy_rewritten_host_is_the_one_twilio_signed():
    out = post(sign_for="https://public.anticipy.example/sms/inbound",
               host="internal-8090.railway.internal",
               headers={"X-Forwarded-Host": "public.anticipy.example",
                        "X-Forwarded-Proto": "https"})
    assert out["status"] == 200, out


def test_a_pinned_env_url_is_still_honoured():
    """The escape hatch survives: an operator can still pin the exact URL."""
    out = post(sign_for="https://pinned.example/sms/inbound",
               host="somewhere-else.example",
               env={"ANTICIPY_TWILIO_WEBHOOK_URL": "https://pinned.example/sms/inbound"})
    assert out["status"] == 200, out


def test_a_wrong_signature_is_refused_and_says_so():
    out = post(sign_for="https://attacker.example/sms/inbound")
    assert out["status"] == 403
    assert not out["saved"]
    joined = " ".join(out["logs"])
    assert "signature mismatch" in joined, joined
    assert "backend.example.com/sms/inbound" in joined, "name the URL we expected"


def test_an_unsigned_request_is_refused_and_named_as_unsigned():
    out = post()
    assert out["status"] == 403
    assert not out["saved"]
    assert "signature missing" in " ".join(out["logs"])


def test_a_forged_signature_from_a_wrong_token_is_refused():
    out = post(sign_for="https://backend.example.com/sms/inbound", token="not-the-token")
    assert out["status"] == 403
    assert not out["saved"]


def test_missing_credentials_503s_loudly_and_names_the_variable():
    out = post(env={"TWILIO_AUTH_TOKEN": ""},
               sign_for="https://backend.example.com/sms/inbound")
    assert out["status"] == 503
    joined = " ".join(out["logs"])
    assert "TWILIO_AUTH_TOKEN" in joined and "not configured" in joined, joined


def test_the_auth_token_never_reaches_a_log_line():
    for out in (post(),
                post(sign_for="https://attacker.example/sms/inbound"),
                post(env={"TWILIO_AUTH_TOKEN": ""})):
        assert AUTH_TOKEN not in json.dumps(out["logs"])


def test_a_text_from_an_unknown_number_is_dropped_but_never_silently():
    """A 200 with empty TwiML and no log reads as a healthy webhook forever."""
    out = post(sign_for="https://backend.example.com/sms/inbound", owner_refs=())
    assert out["status"] == 200
    assert not out["saved"]
    joined = " ".join(out["logs"])
    assert "DROPPED" in joined and "no account owns" in joined, joined


def test_an_ambiguous_number_is_dropped_and_named():
    out = post(sign_for="https://backend.example.com/sms/inbound",
               owner_refs=("own1", "own2"))
    assert out["status"] == 200
    assert not out["saved"]
    assert "ambiguous" in " ".join(out["logs"])


def test_a_retry_is_one_command_and_says_it_recognised_the_retry():
    out = post(sign_for="https://backend.example.com/sms/inbound", duplicate=True)
    assert out["status"] == 200
    assert not out["saved"]
    assert "already handled" in " ".join(out["logs"])


def test_another_accounts_signed_message_is_refused_with_a_reason():
    body = {"AccountSid": "AC" + "9" * 32, "Body": "hi", "From": "+16045550111",
            "MessageSid": "SM" + "a" * 32, "To": NUMBER}
    out = post(body, sign_for="https://backend.example.com/sms/inbound")
    assert out["status"] == 403
    assert "wrong account" in " ".join(out["logs"])


def test_a_message_to_another_number_is_refused_with_a_reason():
    body = {"AccountSid": ACCOUNT, "Body": "hi", "From": "+16045550111",
            "MessageSid": "SM" + "a" * 32, "To": "+15559998888"}
    out = post(body, sign_for="https://backend.example.com/sms/inbound")
    assert out["status"] == 403
    assert "wrong number" in " ".join(out["logs"])


def test_a_wrong_content_type_is_refused():
    out = post(headers={"Content-Type": "application/json"})
    assert out["status"] == 415


# ------------------------------------------------------------------- calling

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
    monkeypatch.setenv("ANTICIPY_PB", "https://backend-production-61e0a.up.railway.app")
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
