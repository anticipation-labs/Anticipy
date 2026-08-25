#!/usr/bin/env python3
"""PROVE that Anticipy's outbound Twilio request is correct, without sending.

Run:  python3 proof/twilio_outbound_proof.py

The only phone number available to test with belongs to the owner, and texting
him to prove a code path is not a test, it is a text. So this stands up a
loopback HTTP server that impersonates Twilio's REST API, points the real
`brain.voice_arm.VoiceArm` at it with TWILIO_API_BASE, and asserts the request
the arm actually built: the URL, the Authorization header, the form parameters.
Nothing leaves the machine — the recorder answers every request itself, and the
account used is Twilio's TEST Account SID, which sends nothing even if someone
later points this at api.twilio.com on purpose.

What it proves, in order:

1. With TWILIO_API_KEY_SID + TWILIO_API_KEY_SECRET set, outbound authenticates
   with the KEY, basic-auth as key-sid:key-secret, against the same
   /2010-04-01/Accounts/{AccountSid}/Messages.json path. The account is in the
   path; the key authenticates AS it.
2. With no key, it falls back to Account SID + auth token, so nothing breaks in
   the window before the owner mints a key.
3. The auth token never appears in a request that used the key.
4. A picture rides as Twilio's own MediaUrl and NOTHING ELSE rides with it —
   exactly {From, To, Body} for a plain send, exactly {From, To, Body,
   MediaUrl} for one carrying a photo. Both exact, so "no extra parameters
   were smuggled in" keeps meaning something now that a parameter was added.
5. A non-+1 destination gets the words and no picture (MMS is US/Canada on
   standard long codes, and stranger_gate leg 3 says foreign strangers really
   do reach production).
6. A send Twilio REFUSED while carrying a picture is retried exactly once,
   without it, with the same Body — and a send carrying no picture is not
   retried at all.
7. A 201 carrying an error_code is a message Twilio ACCEPTED and is never sent
   a second time. TWILIO_MOCK cannot prove any of 4-7: it refuses to send at
   all, so it asserts nothing about a payload (brain/voice_arm.py `_rig_reason`).
8. A call POSTs TwiML that opens with the disclosure.
9. A 400 from Twilio raises SendFailed instead of returning a record — over a
   real HTTP round trip, not a monkeypatched one.
10. Nothing was sent: every request is accounted for by the recorder.

Exit code 0 and a PROVEN line per check, or a stack trace.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# A ROTATED-LOOKING KEY THAT IS NOT A KEY. 32 hex digits in Twilio's SK shape so
# the request is byte-for-byte what a real key produces, with nothing to leak.
KEY_SID = "SK" + "0" * 32
KEY_SECRET = "not-a-real-secret-" + "z" * 14
AUTH_TOKEN = "not-a-real-auth-token-" + "y" * 10
TO = "+15005550001"          # Twilio's test "valid number" magic destination
UK = "+442079460958"         # Ofcom's reserved drama range: nobody's handset
PHOTO = ("https://backend.example/api/files/evidence/"
         "rec1234567890abc/shot_ab12cd34ef.jpg")


class _Twilio(BaseHTTPRequestHandler):
    """Records what was asked of it and answers like Twilio would.

    `queue` answers the NEXT requests with the statuses in it, one each, before
    falling back to `status`. That is what makes the media retry provable: the
    first attempt has to come back not-ok and the second has to come back fine,
    in one call, over a real HTTP round trip.

    `extra` rides on a 2xx body. Twilio really does answer 201 with an
    `error_code` set, and that message IS accepted — resending it is a second
    text to a real person, so the proof has to be able to produce one.
    """

    requests: list[dict] = []
    status = 201
    queue: list = []
    extra: dict = {}

    def do_POST(self):                                   # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode()
        _Twilio.requests.append({
            "path": self.path,
            "authorization": self.headers.get("Authorization") or "",
            "content_type": (self.headers.get("Content-Type") or "").lower(),
            "params": {k: v[0] for k, v in parse_qs(raw, keep_blank_values=True).items()},
        })
        status = _Twilio.queue.pop(0) if _Twilio.queue else _Twilio.status
        body = (json.dumps({"sid": "SM" + "1" * 32, "status": "queued",
                            **_Twilio.extra})
                if status < 400 else
                json.dumps({"code": 21606, "message": "not a valid sender"}))
        payload = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_a):                          # quiet
        return


def basic(user: str, secret: str) -> str:
    return "Basic " + base64.b64encode(f"{user}:{secret}".encode()).decode()


def check(claim: str, condition: bool, detail: str = "") -> None:
    if not condition:
        raise AssertionError(f"NOT PROVEN: {claim}{(' — ' + detail) if detail else ''}")
    print(f"PROVEN  {claim}")


def main() -> int:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Twilio)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    # Every Twilio-relevant variable is set explicitly: an inherited shell
    # export is how a laptop got hold of production credentials in the first
    # place, so this proof refuses to depend on the ambient environment.
    for name in ("TWILIO_API_KEY_SID", "TWILIO_API_KEY_SECRET",
                 "TWILIO_AUTH_TOKEN", "TWILIO_ACCOUNT_SID",
                 "TWILIO_PHONE_NUMBER", "TWILIO_FROM", "TWILIO_MOCK",
                 "TWILIO_API_BASE", "PYTEST_CURRENT_TEST"):
        os.environ.pop(name, None)

    from brain import voice_arm as va

    os.environ["TWILIO_API_BASE"] = base
    os.environ["TWILIO_ACCOUNT_SID"] = va.TEST_ACCOUNT_SID
    os.environ["TWILIO_PHONE_NUMBER"] = va.TEST_FROM_NUMBER
    os.environ["TWILIO_MOCK"] = "false"
    account_path = f"/2010-04-01/Accounts/{va.TEST_ACCOUNT_SID}"

    # ---------------------------------------------------- 1. the API key wins
    os.environ["TWILIO_API_KEY_SID"] = KEY_SID
    os.environ["TWILIO_API_KEY_SECRET"] = KEY_SECRET
    os.environ["TWILIO_AUTH_TOKEN"] = AUTH_TOKEN
    journal: list[str] = []
    arm = va.VoiceArm(journal=journal.append)
    check("the arm reports which credential it will use",
          arm.credential == f"API key {KEY_SID}", arm.credential)
    out = arm.text(TO, "hold that table")
    sent = _Twilio.requests[-1]
    check("the message POSTs to the account's Messages.json",
          sent["path"] == f"{account_path}/Messages.json", sent["path"])
    check("basic auth is key-sid:key-secret, not account-sid:auth-token",
          sent["authorization"] == basic(KEY_SID, KEY_SECRET))
    check("the auth token is nowhere in a key-authenticated request",
          AUTH_TOKEN not in json.dumps(sent))
    check("the body is form-encoded",
          sent["content_type"].startswith("application/x-www-form-urlencoded"),
          sent["content_type"])
    check("From is the configured number",
          sent["params"].get("From") == va.TEST_FROM_NUMBER)
    check("To is the number asked for", sent["params"].get("To") == TO)
    check("Body is the exact text, unmangled",
          sent["params"].get("Body") == "hold that table")
    check("no extra parameters were smuggled in",
          set(sent["params"]) == {"From", "To", "Body"}, str(set(sent["params"])))
    check('a queued message is NOT reported as delivered',
          out["status"] == "queued" and out["delivered"] is False, str(out))

    # --------------------------------------------- 2. the picture, on the wire
    #
    # "no extra parameters were smuggled in" above is the only thing standing
    # between this codebase and a future where an unnoticed parameter rides on
    # every outbound message, and it goes red the moment MediaUrl is wired.
    # DELETING IT IS THE WRONG REPAIR. It is widened instead: EXACTLY
    # {From, To, Body} for a plain send, EXACTLY {From, To, Body, MediaUrl}
    # for one carrying a picture. Two checks, both exact, so "no extra
    # parameters" keeps meaning something.
    arm.text(TO, "that's booked", media=[PHOTO])
    sent = _Twilio.requests[-1]
    check("a picture rides as Twilio's own MediaUrl parameter",
          sent["params"].get("MediaUrl") == PHOTO, str(sent["params"]))
    check("and nothing else rides with it",
          set(sent["params"]) == {"From", "To", "Body", "MediaUrl"},
          str(set(sent["params"])))

    # A foreign stranger reaches production — stranger_gate leg 3 passes — and
    # nobody in this repo has measured what Twilio does with MediaUrl to +44.
    # One of the possibilities is rejecting the whole message, so the picture
    # is not attached and the WORDS still go.
    arm.text(UK, "that's booked", media=[PHOTO])
    sent = _Twilio.requests[-1]
    check("a non-+1 destination is sent the words and no picture",
          set(sent["params"]) == {"From", "To", "Body"}, str(set(sent["params"])))
    check("and it really was the foreign number that got them",
          sent["params"].get("To") == UK)

    # The retry, over a real round trip. Not-ok means Twilio queued nothing.
    before = len(_Twilio.requests)
    _Twilio.queue = [400]
    try:
        arm.text(TO, "that's booked")
    except va.SendFailed:
        pass
    check("a send carrying NO picture is not retried — the retry exists to "
          "drop one, and without one it is only a second text",
          len(_Twilio.requests) - before == 1, str(len(_Twilio.requests) - before))
    _Twilio.queue = [400]
    out = arm.text(TO, "that's booked", media=[PHOTO])
    attempts = _Twilio.requests[-2:]
    check("a refused picture costs the picture and not the confirmation",
          len(_Twilio.requests) - before == 3 and out["status"] == "queued",
          str(out))
    check("the first attempt carried it and the retry did not",
          attempts[0]["params"].get("MediaUrl") == PHOTO
          and "MediaUrl" not in attempts[1]["params"],
          str([sorted(a["params"]) for a in attempts]))
    check("the retry is the SAME sentence, minus the picture",
          attempts[1]["params"].get("Body") == "that's booked")

    # ...and the one that must NOT be retried. A 201 with an error_code is a
    # message Twilio ACCEPTED; resending it texts a real person twice, and this
    # product has a recorded incident of exactly that.
    _Twilio.extra = {"error_code": 30008}
    before = len(_Twilio.requests)
    try:
        arm.text(TO, "that's booked", media=[PHOTO])
    except va.SendFailed:
        pass
    else:
        raise AssertionError("NOT PROVEN: a 201 with an error_code was a success")
    check("a message Twilio ACCEPTED is never sent a second time",
          len(_Twilio.requests) - before == 1,
          str(len(_Twilio.requests) - before))
    _Twilio.extra = {}

    # ------------------------------------------- 2. the auth token still works
    del os.environ["TWILIO_API_KEY_SID"]
    del os.environ["TWILIO_API_KEY_SECRET"]
    fallback = va.VoiceArm(journal=journal.append)
    check("with no key, outbound falls back to the auth token",
          fallback.credential.startswith("account auth token"), fallback.credential)
    fallback.text(TO, "fallback still sends")
    check("the fallback authenticates as account-sid:auth-token",
          _Twilio.requests[-1]["authorization"]
          == basic(va.TEST_ACCOUNT_SID, AUTH_TOKEN))

    # ------------------------------------------------- 3. a call, still scripted
    plan = va.CallPlan(
        to=TO, goal="hold a table for two at 7:30 tonight",
        script="I'd like to hold a table for two at 7:30 tonight, please.",
        callee="Earls Kitchen, Yaletown", approved_by_owner=True,
        on_behalf_of="Omar")
    arm = va.VoiceArm(journal=journal.append)
    arm.call(plan)
    dialed = _Twilio.requests[-1]
    check("the call POSTs to the account's Calls.json",
          dialed["path"] == f"{account_path}/Calls.json", dialed["path"])
    check("the TwiML discloses itself before the script",
          dialed["params"].get("Twiml", "").index("automated assistant")
          < dialed["params"].get("Twiml", "").index("hold a table"))

    # ------------------------------------------------- 4. a refusal is a failure
    _Twilio.status = 400
    try:
        arm.text(TO, "this one is refused")
    except va.SendFailed as exc:
        check("a 400 from Twilio raises instead of returning a record",
              "21606" in str(exc), str(exc))
    else:
        raise AssertionError("NOT PROVEN: a 400 was treated as a sent message")
    _Twilio.status = 201

    # ------------------------------------------------------- 5. nothing was sent
    check("every request was answered by the loopback recorder, so no message "
          "and no call reached Twilio",
          len(_Twilio.requests) == 10 and base.startswith("http://127.0.0.1:"),
          f"{len(_Twilio.requests)} recorded, expected 10")
    server.shutdown()
    print(f"\n{len(_Twilio.requests)} requests recorded on {base}; 0 sent. "
          f"Account {va.TEST_ACCOUNT_SID} is Twilio's TEST account.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
