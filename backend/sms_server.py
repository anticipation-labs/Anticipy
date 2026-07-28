"""Anticipy SMS channel.

Inbound: Twilio webhook -> validates signature -> routes the free-form reply
through the conversational brain (brain/conversation.py) so texting Anticipy
is a real chat, not a YES/NO wall. Keyword fallback stays for keyless runs.
Outbound: send_sms() is how Anticipy texts you like a human.
"""
import os
import sys
from pathlib import Path

import httpx
from fastapi import FastAPI, Form, Request, Response
from twilio.request_validator import RequestValidator
from twilio.rest import Client

PB = os.environ.get("ANTICIPY_PB", "http://127.0.0.1:8090")
ACCOUNT_SID = os.environ["TWILIO_ACCOUNT_SID"]
AUTH_TOKEN = os.environ["TWILIO_AUTH_TOKEN"]
API_KEY_SID = os.environ.get("TWILIO_API_KEY_SID")
API_KEY_SECRET = os.environ.get("TWILIO_API_KEY_SECRET")
FROM_NUMBER = os.environ["TWILIO_PHONE_NUMBER"]

if API_KEY_SID and API_KEY_SECRET:
    client = Client(API_KEY_SID, API_KEY_SECRET, ACCOUNT_SID)
else:
    client = Client(ACCOUNT_SID, AUTH_TOKEN)

validator = RequestValidator(AUTH_TOKEN)
app = FastAPI()

YES_WORDS = {"yes", "y", "yes.", "send it", "send", "book it", "do it", "go", "confirm"}

# Conversational brain: one Anticipy + one Conversation per server, sharing
# the same memory and job queue the pendant path uses.
_convo = None


def get_conversation():
    global _convo
    if _convo is None:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from brain.anticipy_core import Anticipy
        from brain.conversation import Conversation
        from brain.llm import LLM

        llm = LLM()
        anticipy = Anticipy(llm=llm if llm.live else None, backend_url=PB)
        _convo = Conversation(anticipy, transport=_SMSTransport())
        anticipy.conversation = _convo
    return _convo


class _SMSTransport:
    """Inbound replies go back via TwiML (the webhook response), so the
    transport only actually sends for PROACTIVE reach-outs, where there is no
    webhook response to ride on."""

    def __init__(self):
        self.suppress = False  # set during webhook handling

    def send(self, to: str, body: str) -> dict:
        if self.suppress:
            return {"to": to, "body": body, "via": "twiml"}
        return {"sid": send_sms(to, body), "to": to, "body": body}


def send_sms(to: str, body: str) -> str:
    msg = client.messages.create(to=to, from_=FROM_NUMBER, body=body)
    return msg.sid


@app.post("/sms/inbound")
async def inbound(request: Request, From: str = Form(...), Body: str = Form(...)):
    form = dict(await request.form())
    url = str(request.url).replace("http://", "https://", 1)
    sig = request.headers.get("X-Twilio-Signature", "")
    if not validator.validate(url, form, sig):
        return Response(status_code=403)

    text = Body.strip()
    # Conversational path: the LLM understands the free-form reply against
    # the pending jobs and drafts Anticipy's next text; the queue flip
    # (release/cancel) happens in code, never in the model.
    try:
        convo = get_conversation()
        convo.transport.suppress = True
        try:
            out = convo.on_reply(From, text)
        finally:
            convo.transport.suppress = False
        reply = out["reply"]
        decision = out["intent"]
    except Exception:
        # Keyword fallback if the brain is unavailable.
        confirmed = text.lower() in YES_WORDS
        decision = "confirm" if confirmed else "message"
        reply = "On it." if confirmed else "Got it."
        if confirmed:
            async with httpx.AsyncClient() as c:
                r = await c.get(f"{PB}/api/collections/jobs/records",
                                params={"filter": "status='awaiting_confirm'", "perPage": 1,
                                        "sort": "-created"})
                items = r.json().get("items", [])
                if items:
                    await c.patch(f"{PB}/api/collections/jobs/records/{items[0]['id']}",
                                  json={"status": "queued"})

    async with httpx.AsyncClient() as c:
        await c.post(f"{PB}/api/collections/events/records", json={
            "device_id": "sms", "kind": "sms_reply", "text": text,
            "decision": decision,
        })

    return Response(
        content=f"<?xml version='1.0' encoding='UTF-8'?><Response><Message>{reply}</Message></Response>",
        media_type="application/xml",
    )


@app.get("/health")
def health():
    return {"ok": True}
