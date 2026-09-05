#!/usr/bin/env python3
"""PROVE that Anticipy's outbound Sendblue request is correct, without sending.

Run:  python3 proof/sendblue_outbound_proof.py

The twin of proof/twilio_outbound_proof.py, for the same reason: the only
phone number available to test with belongs to the owner, and texting him to
prove a code path is not a test, it is a text. So this stands up a loopback
HTTP server that impersonates Sendblue's send-message API, points the real
`brain.sendblue_arm.SendblueArm` at it with SENDBLUE_API_BASE, drives it
through the real transport and `Conversation.say()` — the path the worker
takes — and asserts the request the arm actually built: the path, the two
headers, every field of the JSON. Nothing leaves the machine; the recorder
answers every request itself.

What it proves, in order:

1. The message POSTs JSON to /api/send-message with `sb-api-key-id` and
   `sb-api-secret-key` and EXACTLY {from_number, number, content} — exact, so
   "no extra fields were smuggled in" keeps meaning something.
2. The recorder never sees the secret's VALUE in anything it keeps: it records
   whether the header matched, as a boolean. The secret is in no journal line
   and no exception text, including a 401 whose body echoes it back.
3. A picture rides as Sendblue's own `media_url` and NOTHING ELSE rides with
   it; a non-+1 destination gets the words and no picture.
4. A send Sendblue did NOT take while carrying a picture — a non-2xx, or a
   2xx whose status is a documented not-sent one (ERROR, DECLINED) — is
   retried exactly once, without it, with the same content. A send carrying
   no picture is not retried at all.
5. A 2xx with a LIVE status and an error_code is a message Sendblue HAS. It
   raises, and it is never sent a second time.
6. A 200 whose status is ERROR raises SendFailed through say() instead of
   returning a record, so a failed text never reads as delivered. A queued
   one is NOT reported as delivered; a DELIVERED one is.
7. A 401 raises, names the key by its tail, and does not name the secret.
8. SENDBLUE_STATUS_CALLBACK rides as `status_callback` when set, and only then.
9. ANTICIPY_SMS_MOCK refuses the send before any request — ahead of the
   loopback exemption — and TWILIO_MOCK does the same for this arm.
10. Nothing was sent: every request is accounted for by the recorder.

Exit code 0 and a PROVEN line per check, or a stack trace.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# A KEY THAT IS NOT A KEY. Shaped like one, with a tail the banner can show.
KEY_ID = "sbkey-" + "0" * 20 + "1234"
SECRET = "not-a-real-secret-" + "z" * 14
FROM = "+15005550006"        # Twilio's test From number: nobody's handset
TO = "+15005550001"          # Twilio's test "valid number" magic destination
UK = "+442079460958"         # Ofcom's reserved drama range: nobody's handset
PHOTO = ("https://backend.example/api/files/evidence/"
         "rec1234567890abc/shot_ab12cd34ef.jpg")
HANDLE = "mh_" + "1" * 24


class _Sendblue(BaseHTTPRequestHandler):
    """Records what was asked of it and answers like Sendblue would.

    `queue` answers the NEXT requests, one each, before falling back to
    `status`/`reply`: an int is an HTTP status with the default body, a
    (status, body) pair overrides the body too. That is what makes the media
    retry provable over a real round trip.

    THE SECRET IS RECORDED AS A BOOLEAN. `secret_matches` says whether the
    header was right; the value itself is kept nowhere, so a printed
    recorder can never be the leak this proof exists to rule out.
    """

    requests: list[dict] = []
    status = 200
    reply: dict = {}
    queue: list = []

    def do_POST(self):                                   # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode()
        try:
            body = json.loads(raw)
        except ValueError:
            body = None
        _Sendblue.requests.append({
            "path": self.path,
            "content_type": (self.headers.get("Content-Type") or "").lower(),
            "key_id": self.headers.get("sb-api-key-id") or "",
            "secret_present": bool(self.headers.get("sb-api-secret-key")),
            "secret_matches": (self.headers.get("sb-api-secret-key") or "") == SECRET,
            "body": body,
            "raw_carries_secret": SECRET in raw,
        })
        nxt = _Sendblue.queue.pop(0) if _Sendblue.queue else (_Sendblue.status, _Sendblue.reply)
        if isinstance(nxt, int):
            nxt = (nxt, _Sendblue.reply)
        status, extra = nxt
        if status >= 400:
            # A vendor error body that ECHOES A HEADER is the leak shape the
            # scrub exists for; the 401 below proves it never reaches a log.
            payload = {"status": "ERROR", "error_code": status,
                       "error_message": f"unauthorized: {SECRET}" if status == 401
                       else "invalid request"}
        else:
            payload = {"message_handle": HANDLE, "status": "QUEUED",
                       "number": (body or {}).get("number"), **extra}
        out = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *_a):                          # quiet
        return


def check(claim: str, condition: bool, detail: str = "") -> None:
    if not condition:
        raise AssertionError(f"NOT PROVEN: {claim}{(' — ' + detail) if detail else ''}")
    print(f"PROVEN  {claim}")


def main() -> int:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Sendblue)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    # Every relevant variable is set explicitly: an inherited shell export is
    # how a laptop got hold of production credentials in the first place, so
    # this proof refuses to depend on the ambient environment.
    for name in ("SENDBLUE_API_KEY_ID", "SENDBLUE_API_SECRET_KEY",
                 "SENDBLUE_FROM_NUMBER", "SENDBLUE_API_BASE",
                 "SENDBLUE_STATUS_CALLBACK", "ANTICIPY_SMS_MOCK", "TWILIO_MOCK",
                 "ANTICIPY_SMS_PROVIDER", "TWILIO_API_BASE", "ANTICIPY_PB",
                 "PYTEST_CURRENT_TEST"):
        os.environ.pop(name, None)

    from brain import sendblue_arm as sb
    from brain import voice_arm as va
    from brain.conversation import Conversation, MessageTransport

    os.environ["SENDBLUE_API_BASE"] = base
    os.environ["SENDBLUE_API_KEY_ID"] = KEY_ID
    os.environ["SENDBLUE_API_SECRET_KEY"] = SECRET
    os.environ["SENDBLUE_FROM_NUMBER"] = FROM

    journal: list[str] = []
    raised: list[str] = []

    def convo_over(arm):
        """The worker's path: Conversation.say -> MessageTransport.send ->
        arm.text. No owner identity, so nothing reaches a backend."""
        anticipy = types.SimpleNamespace(llm=None, owner_ref="", owner_id="")
        return Conversation(anticipy, transport=MessageTransport(arm))

    # ------------------------------------------------ 1. the request, exactly
    arm = sb.SendblueArm(journal=journal.append)
    check("the arm names its credential by the key's tail",
          arm.credential == "Sendblue key …1234", arm.credential)
    out = convo_over(arm).say(TO, "hold that table")
    sent = _Sendblue.requests[-1]
    check("the message POSTs to Sendblue's send-message path",
          sent["path"] == "/api/send-message", sent["path"])
    check("the body is JSON", sent["content_type"].startswith("application/json"),
          sent["content_type"])
    check("sb-api-key-id carries the key id", sent["key_id"] == KEY_ID)
    check("sb-api-secret-key carries the secret (recorded as a match, never a value)",
          sent["secret_present"] and sent["secret_matches"])
    check("from_number is the configured Sendblue number",
          sent["body"].get("from_number") == FROM)
    check("number is the number asked for", sent["body"].get("number") == TO)
    check("content is the exact text, unmangled",
          sent["body"].get("content") == "hold that table")
    check("no extra fields were smuggled in",
          set(sent["body"]) == {"from_number", "number", "content"},
          str(set(sent["body"])))
    check("a queued message is NOT reported as delivered",
          out == {"sid": HANDLE, "status": "queued", "delivered": False}, str(out))
    check("the secret is in no request body", not sent["raw_carries_secret"])

    # ------------------------------------------------ 2. the picture, on the wire
    arm.text(TO, "that's booked", media=[PHOTO])
    sent = _Sendblue.requests[-1]
    check("a picture rides as Sendblue's own media_url field",
          sent["body"].get("media_url") == PHOTO, str(sent["body"]))
    check("and nothing else rides with it",
          set(sent["body"]) == {"from_number", "number", "content", "media_url"},
          str(set(sent["body"])))
    arm.text(UK, "that's booked", media=[PHOTO])
    sent = _Sendblue.requests[-1]
    check("a non-+1 destination is sent the words and no picture",
          set(sent["body"]) == {"from_number", "number", "content"},
          str(set(sent["body"])))
    check("and it really was the foreign number that got them",
          sent["body"].get("number") == UK)

    # ------------------------------------------------------- 3. the retry
    before = len(_Sendblue.requests)
    _Sendblue.queue = [400]
    try:
        arm.text(TO, "that's booked")
    except va.SendFailed:
        pass
    else:
        raise AssertionError("NOT PROVEN: a 400 was treated as a sent message")
    check("a send carrying NO picture is not retried — the retry exists to "
          "drop one, and without one it is only a second text",
          len(_Sendblue.requests) - before == 1, str(len(_Sendblue.requests) - before))

    _Sendblue.queue = [400]
    out = arm.text(TO, "that's booked", media=[PHOTO])
    attempts = _Sendblue.requests[-2:]
    check("a refused picture (non-2xx) costs the picture and not the confirmation",
          len(_Sendblue.requests) - before == 3 and out["status"] == "queued", str(out))
    check("the first attempt carried it and the retry did not",
          attempts[0]["body"].get("media_url") == PHOTO
          and "media_url" not in attempts[1]["body"],
          str([sorted(a["body"]) for a in attempts]))
    check("the retry is the SAME sentence, minus the picture",
          attempts[1]["body"].get("content") == "that's booked")

    # A 200 whose status Sendblue documents as not-sent is ALSO certain: no
    # message is on its way, so dropping the picture cannot double-text.
    before = len(_Sendblue.requests)
    _Sendblue.queue = [(200, {"status": "ERROR", "error_code": 4004,
                              "error_message": "media could not be fetched"})]
    out = arm.text(TO, "that's booked", media=[PHOTO])
    attempts = _Sendblue.requests[-2:]
    check("a 200 with status ERROR while carrying a picture is retried once, "
          "without it", len(_Sendblue.requests) - before == 2
          and out["status"] == "queued" and "media_url" not in attempts[1]["body"],
          str(out))

    # ...and the one that must NOT be retried: a live status with an
    # error_code is a message Sendblue HAS. Resending it texts a real person
    # twice, and this product has a recorded incident of exactly that.
    before = len(_Sendblue.requests)
    _Sendblue.queue = [(200, {"status": "QUEUED", "error_code": 9001})]
    try:
        arm.text(TO, "that's booked", media=[PHOTO])
    except va.SendFailed:
        pass
    else:
        raise AssertionError("NOT PROVEN: a queued message with an error_code was a success")
    check("a message Sendblue ACCEPTED with an error_code raises and is never "
          "sent a second time", len(_Sendblue.requests) - before == 1,
          str(len(_Sendblue.requests) - before))

    # ------------------------------------------ 4. a failure is never a record
    _Sendblue.queue = [(200, {"status": "ERROR", "error_code": 4001,
                              "error_message": "number not on iMessage or SMS"})]
    try:
        convo_over(arm).say(TO, "this one fails")
    except va.SendFailed as exc:
        raised.append(str(exc))
        check("a 200 whose status is ERROR raises SendFailed through say() "
              "instead of returning a record",
              "status=error" in str(exc) and "4001" in str(exc), str(exc))
    else:
        raise AssertionError("NOT PROVEN: a status ERROR reply came back as a record")
    _Sendblue.queue = [(200, {"status": "DECLINED"})]
    try:
        arm.text(TO, "this one is declined")
    except va.SendFailed as exc:
        raised.append(str(exc))
        check("DECLINED is a failure too", "declined" in str(exc), str(exc))
    else:
        raise AssertionError("NOT PROVEN: DECLINED came back as a record")
    _Sendblue.queue = [(200, {"status": "DELIVERED"})]
    out = arm.text(TO, "already there")
    check("only a status that means a handset saw it reads as delivered",
          out["delivered"] is True and out["status"] == "delivered", str(out))

    # ------------------------------------------------------ 5. the credential
    _Sendblue.queue = [401]
    try:
        arm.text(TO, "wrong key")
    except va.SendFailed as exc:
        raised.append(str(exc))
        check("a 401 raises, names the key's tail, and does not name the secret",
              "401" in str(exc) and "…1234" in str(exc) and SECRET not in str(exc),
              str(exc))
    else:
        raise AssertionError("NOT PROVEN: a 401 was treated as a sent message")

    # ------------------------------------------------- 6. the status callback
    os.environ["SENDBLUE_STATUS_CALLBACK"] = "https://backend.example/sms/sendblue/status"
    with_callback = sb.SendblueArm(journal=journal.append)
    with_callback.text(TO, "with a callback")
    sent = _Sendblue.requests[-1]
    check("SENDBLUE_STATUS_CALLBACK rides as status_callback, and only then",
          sent["body"].get("status_callback") == os.environ["SENDBLUE_STATUS_CALLBACK"]
          and set(sent["body"]) == {"from_number", "number", "content", "status_callback"},
          str(set(sent["body"])))
    del os.environ["SENDBLUE_STATUS_CALLBACK"]

    # ------------------------------------------------------- 7. the muzzles
    before = len(_Sendblue.requests)
    for flag in ("ANTICIPY_SMS_MOCK", "TWILIO_MOCK"):
        os.environ[flag] = "1"
        muzzled = sb.SendblueArm(journal=journal.append)
        try:
            muzzled.text(TO, "must not go")
        except va.SendFailed as exc:
            raised.append(str(exc))
            check(f"{flag} refuses the send before any request, ahead of the "
                  "loopback exemption", flag in str(exc), str(exc))
        else:
            raise AssertionError(f"NOT PROVEN: {flag} did not muzzle the arm")
        del os.environ[flag]
    check("a muzzled arm made no request at all",
          len(_Sendblue.requests) == before, str(len(_Sendblue.requests) - before))

    # ------------------------------------------------------- 8. the secret
    leaks = [line for line in journal + raised if SECRET in line]
    check("the secret appears in no journal line and no exception text — "
          "including the 401 whose body echoed it", not leaks, str(leaks)[:200])
    check("the secret appears in no recorded request body",
          not any(r["raw_carries_secret"] for r in _Sendblue.requests))

    # ------------------------------------------------------- 9. nothing was sent
    # 1 plain + 2 pictures + 1 (400, no picture) + 2 (400 then ok) + 2 (ERROR
    # then ok) + 1 (queued+error_code) + 1 ERROR + 1 DECLINED + 1 DELIVERED
    # + 1 (401) + 1 callback + 0 muzzled. Exact, so a stray send has nowhere
    # to hide.
    expected = 14
    check("every request was answered by the loopback recorder, so no message "
          "reached Sendblue",
          len(_Sendblue.requests) == expected and base.startswith("http://127.0.0.1:"),
          f"{len(_Sendblue.requests)} recorded, expected {expected}")
    server.shutdown()
    print(f"\n{len(_Sendblue.requests)} requests recorded on {base}; 0 sent. "
          f"Key {sb.key_tail(KEY_ID)} is not a key.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
