"""TextChannel — SMS over Twilio.

LIVE (ANTICIPY_CHANNELS_MODE=live + TWILIO_ACCOUNT_SID/AUTH_TOKEN/FROM present): a real SMS
via Twilio's REST API. Otherwise MOCK: records the message in `.sent` and returns sent=mock —
free, deterministic, CI-safe. The ONE controlled real proof needs the user's creds + a test
number (a one-time human action). Every send (real or mock) is appended to `.sent` for the log.
"""
from __future__ import annotations

import os
import urllib.parse
import urllib.request
from typing import List

from .base import Channel


class TextChannel(Channel):
    name = "text"

    def __init__(self) -> None:
        self.sent: List[dict] = []   # audit log of every send (real or mock)

    def _live(self) -> bool:
        return (os.environ.get("ANTICIPY_CHANNELS_MODE") == "live"
                and bool(os.environ.get("TWILIO_ACCOUNT_SID"))
                and bool(os.environ.get("TWILIO_AUTH_TOKEN"))
                and bool(os.environ.get("TWILIO_FROM")))

    def send(self, to: str, message: str) -> dict:
        if not self._live():
            rec = {"sent": True, "mock": True, "channel": self.name, "to": to, "message": message}
            self.sent.append(rec)
            return rec
        rec = self._twilio_send(to, message)   # pragma: no cover (live-only; needs creds + a real number)
        self.sent.append(rec)
        return rec

    def _twilio_send(self, to: str, message: str) -> dict:   # pragma: no cover
        sid = os.environ["TWILIO_ACCOUNT_SID"]
        token = os.environ["TWILIO_AUTH_TOKEN"]
        url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
        data = urllib.parse.urlencode({"To": to, "From": os.environ["TWILIO_FROM"], "Body": message}).encode()
        req = urllib.request.Request(url, data=data)
        auth = urllib.request.HTTPBasicAuthHandler()
        auth.add_password("Twilio API", url, sid, token)
        try:
            with urllib.request.build_opener(auth).open(req, timeout=15) as r:
                body = r.read().decode()
            return {"sent": True, "mock": False, "channel": self.name, "to": to, "message": message, "twilio": body[:200]}
        except Exception as e:
            return {"sent": False, "mock": False, "channel": self.name, "to": to, "message": message, "error": str(e)}
