"""Anticipy's voice arm: she can text and call — you, or anyone you ask her to.

Thin Twilio REST wrapper (no SDK): SMS via Messages, real phone calls via
Calls with inline TwiML so she speaks in her own voice. Credentials come from
the environment; nothing is hardcoded.
"""
from __future__ import annotations

import os
from xml.sax.saxutils import escape

import requests


class VoiceArm:
    def __init__(self):
        self.sid = os.environ["TWILIO_ACCOUNT_SID"]
        self.token = os.environ["TWILIO_AUTH_TOKEN"]
        self.from_number = os.environ["TWILIO_PHONE_NUMBER"]
        self.base = f"https://api.twilio.com/2010-04-01/Accounts/{self.sid}"

    def text(self, to: str, body: str) -> dict:
        r = requests.post(
            f"{self.base}/Messages.json",
            auth=(self.sid, self.token),
            data={"From": self.from_number, "To": to, "Body": body},
            timeout=15,
        )
        r.raise_for_status()
        out = r.json()
        return {"sid": out["sid"], "status": out["status"]}

    def call(self, to: str, say: str, voice: str = "Polly.Joanna") -> dict:
        """Place a real call and speak `say` when it's answered."""
        twiml = f'<Response><Say voice="{voice}">{escape(say)}</Say></Response>'
        r = requests.post(
            f"{self.base}/Calls.json",
            auth=(self.sid, self.token),
            data={"From": self.from_number, "To": to, "Twiml": twiml},
            timeout=15,
        )
        r.raise_for_status()
        out = r.json()
        return {"sid": out["sid"], "status": out["status"]}
