"""CallChannel — voice over Twilio Calls, spoken with inline TwiML <Say>.

LIVE (ANTICIPY_CHANNELS_MODE=live + TWILIO_ACCOUNT_SID/AUTH_TOKEN/FROM present): a real
outbound call via Twilio's REST API — researched shape: POST
/2010-04-01/Accounts/{sid}/Calls.json with form params To / From /
Twiml=<Response><Say>...</Say></Response> (Twiml capped at 4000 chars), HTTP basic auth;
the JSON response carries the call `sid` and `status` (queued/ringing/.../completed),
which is the read-back handle gate_P3 verifies. Otherwise MOCK: records the call in
`.sent` and returns sent=mock — free, deterministic, CI-safe. Every send (real or mock)
is appended to `.sent` for the audit trail, exactly like text.py.
"""
from __future__ import annotations

import base64
import json
import os
import urllib.parse
import urllib.request
from typing import List
from xml.sax.saxutils import escape

from .base import Channel


class CallChannel(Channel):
    name = "call"

    def __init__(self) -> None:
        self.sent: List[dict] = []   # audit log of every call (real or mock)

    def _live(self) -> bool:
        return (os.environ.get("ANTICIPY_CHANNELS_MODE") == "live"
                and bool(os.environ.get("TWILIO_ACCOUNT_SID"))
                and bool(os.environ.get("TWILIO_AUTH_TOKEN"))
                and bool(os.environ.get("TWILIO_FROM")))

    @staticmethod
    def twiml(message: str) -> str:
        """Inline TwiML for the call: say the message. The text is XML-escaped and
        bounded well under Twilio's 4000-char Twiml parameter cap."""
        return f"<Response><Say>{escape(message[:3000])}</Say></Response>"

    def send(self, to: str, message: str) -> dict:
        if not self._live():
            rec = {"sent": True, "mock": True, "channel": self.name, "to": to, "message": message}
            self.sent.append(rec)
            return rec
        rec = self._twilio_call(to, message)   # pragma: no cover (live-only; needs creds + a real number)
        self.sent.append(rec)
        return rec

    def _twilio_call(self, to: str, message: str) -> dict:   # pragma: no cover
        sid = os.environ["TWILIO_ACCOUNT_SID"]
        token = os.environ["TWILIO_AUTH_TOKEN"]
        url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Calls.json"
        data = urllib.parse.urlencode({"To": to, "From": os.environ["TWILIO_FROM"],
                                       "Twiml": self.twiml(message)}).encode()
        req = urllib.request.Request(url, data=data)
        # Explicit basic-auth header: HTTPBasicAuthHandler only answers a 401 whose
        # realm matches, which is an avoidable live failure mode for a first call.
        req.add_header("Authorization",
                       "Basic " + base64.b64encode(f"{sid}:{token}".encode()).decode())
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                body = json.loads(r.read().decode())
            return {"sent": True, "mock": False, "channel": self.name, "to": to,
                    "message": message, "call_sid": body.get("sid"), "status": body.get("status")}
        except Exception as e:
            return {"sent": False, "mock": False, "channel": self.name, "to": to,
                    "message": message, "error": str(e)}
