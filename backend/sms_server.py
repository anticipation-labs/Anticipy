"""Anticipy SMS channel.

Inbound: Twilio webhook -> validates signature -> stores the message as an
event in PocketBase (so the brain can treat your reply as a confirmation).
Outbound: send_sms() is how Anticipy texts you like a human.
"""
import os

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
    confirmed = text.lower() in YES_WORDS
    async with httpx.AsyncClient() as c:
        await c.post(f"{PB}/api/collections/events/records", json={
            "device_id": "sms", "kind": "sms_reply", "text": text,
            "decision": "confirm" if confirmed else "message",
        })
        if confirmed:
            r = await c.get(f"{PB}/api/collections/jobs/records",
                            params={"filter": "status='awaiting_confirm'", "perPage": 1,
                                    "sort": "-created"})
            items = r.json().get("items", [])
            if items:
                await c.patch(f"{PB}/api/collections/jobs/records/{items[0]['id']}",
                              json={"status": "queued"})

    reply = "On it." if confirmed else "Got it."
    return Response(
        content=f"<?xml version='1.0' encoding='UTF-8'?><Response><Message>{reply}</Message></Response>",
        media_type="application/xml",
    )


@app.get("/health")
def health():
    return {"ok": True}
