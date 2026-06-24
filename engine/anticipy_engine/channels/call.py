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

    @staticmethod
    def configured() -> bool:
        return bool(os.environ.get("TWILIO_ACCOUNT_SID")
                    and os.environ.get("TWILIO_AUTH_TOKEN")
                    and os.environ.get("TWILIO_FROM"))

    def _live(self) -> bool:
        return os.environ.get("ANTICIPY_CHANNELS_MODE") == "live" and self.configured()

    @staticmethod
    def twiml(message: str) -> str:
        """Inline TwiML for the call: say the message. The text is XML-escaped and
        bounded well under Twilio's 4000-char Twiml parameter cap.

        This is the ONE-SHOT, no-LLM FALLBACK: Twilio just speaks one fixed line and
        hangs up ("calendar event made; I'll call you at 2:45"). Used when there is no
        public wss URL to attach a ConversationRelay socket — it needs no brain and no
        live socket, so it can never strand a call mid-turn.

        Voice: a NATURAL Twilio Polly neural voice (not the robotic default), tunable via
        ANTICIPY_CALL_VOICE. Donna-from-Suits is female, so the default is Joanna-Neural."""
        voice = (os.environ.get("ANTICIPY_CALL_VOICE") or "Polly.Joanna-Neural").strip()
        return f'<Response><Say voice="{escape(voice)}">{escape(message[:3000])}</Say></Response>'

    @staticmethod
    def conversation_relay_twiml(ws_url: str, greeting: str) -> str:
        """Two-way TwiML: hand the live call to Twilio ConversationRelay over a websocket.

        Researched shape (Twilio ConversationRelay): a <Connect> verb wrapping a single
        <ConversationRelay> with the websocket ``url`` (must be wss://) and an optional
        ``welcomeGreeting`` Twilio speaks before the first owner turn. Twilio then runs
        the ASR+TTS and exchanges JSON frames with that socket — owner speech arrives as
        {type:"prompt", voicePrompt}, our reply streams back as {type:"text", token}, and
        the turn closes with {type:"end"}. Attributes are XML-escaped (quotes too, since
        they sit inside double-quoted attributes); the greeting is bounded like the <Say>
        path so the whole TwiML stays well under Twilio's 4000-char cap.

        This is the two-way UPGRADE of ``twiml`` — same call, but the owner can answer and
        be answered instead of only being spoken at. ``twiml`` stays the fallback when no
        public wss URL exists for the /cr endpoint."""
        url = escape(ws_url, {'"': "&quot;"})
        greet = escape(greeting[:1500], {'"': "&quot;"})
        # PREMIUM VOICE: Twilio ConversationRelay has ElevenLabs TTS built in (no separate ElevenLabs key —
        # Twilio bills it), so we default to a natural ElevenLabs voice for the "can't tell it's AI" bar.
        # Both are env-overridable; voice may be "<voiceId>" or "<voiceId>-<modelId>" (turbo/flash = low
        # latency, sub-second turns). Set ANTICIPY_CR_TTS_PROVIDER="" to fall back to Twilio's basic voice.
        tts = escape((os.environ.get("ANTICIPY_CR_TTS_PROVIDER", "ElevenLabs")).strip(), {'"': "&quot;"})
        voice = escape((os.environ.get("ANTICIPY_CR_VOICE", "21m00Tcm4TlvDq8ikWAM-eleven_turbo_v2_5")).strip(),
                       {'"': "&quot;"})
        attrs = f'url="{url}" welcomeGreeting="{greet}"'
        if tts:
            attrs += f' ttsProvider="{tts}"'
        if voice:
            attrs += f' voice="{voice}"'
        return f"<Response><Connect><ConversationRelay {attrs} /></Connect></Response>"

    def call_twiml(self, message: str) -> str:
        """Pick the TwiML for an outbound call: two-way ConversationRelay when a public
        websocket URL for the /cr endpoint is configured (ANTICIPY_CR_WSS_URL=wss://...),
        else the one-shot <Say> fallback. The message doubles as the welcome greeting on
        the two-way path, so the owner hears the same opening line either way."""
        ws_url = (os.environ.get("ANTICIPY_CR_WSS_URL") or "").strip()
        if ws_url.startswith("wss://"):
            return self.conversation_relay_twiml(ws_url, message)
        return self.twiml(message)

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
                                       "Twiml": self.call_twiml(message)}).encode()
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
