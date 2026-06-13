"""Channels seam test — text/call are REAL channels in mock mode; app stays a stub.

Mock mode (no ANTICIPY_CHANNELS_MODE=live): every send succeeds deterministically,
is flagged mock, and lands in the `.sent` audit trail — zero network. The live paths
are env-gated off here. CallChannel's TwiML builder is pinned (XML escaping + the
4000-char Twiml parameter bound), since that string is what Twilio will speak.

Run:  PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_channels.py
"""
import os

# force mock: the suite must never construct a Twilio transport
os.environ.pop("ANTICIPY_CHANNELS_MODE", None)

from anticipy_engine.channels import Channels  # noqa: E402
from anticipy_engine.channels.base import Channel  # noqa: E402
from anticipy_engine.channels.call import CallChannel  # noqa: E402
from anticipy_engine.channels.text import TextChannel  # noqa: E402

ch = Channels()
assert {ch.call.name, ch.text.name, ch.app.name} == {"call", "text", "app"}

# text + call: REAL channels in mock mode — send succeeds, is honest about mock,
# and the audit trail records it
for c, to in [(ch.call, "+15551234567"), (ch.text, "+15551234567")]:
    assert isinstance(c, Channel)
    assert not c._live(), "live mode must require ANTICIPY_CHANNELS_MODE=live + creds"
    out = c.send(to, "your 3pm moved")
    assert out["sent"] is True and out["mock"] is True, out
    assert out["channel"] == c.name and out["to"] == to, out
    assert c.sent and c.sent[-1] is out, "every send must land in the .sent audit log"

# app: still a scaffold stub (no real device push yet)
out = ch.app.send("device", "your 3pm moved")
assert out["sent"] is False and out["stub"] is True, out

# TwiML: escaped + bounded (the Twiml param caps at 4000 chars)
twiml = CallChannel.twiml('Reply <YES> & "go"')
assert twiml.startswith("<Response><Say>") and twiml.endswith("</Say></Response>"), twiml
assert "<YES>" not in twiml and "&amp;" in twiml and "&lt;YES&gt;" in twiml, twiml
assert len(CallChannel.twiml("x" * 10000)) < 4000, "Twiml parameter bound violated"

# Readiness: status surfaces can detect live-ready configuration without sending.
prev = {k: os.environ.get(k) for k in (
    "ANTICIPY_CHANNELS_MODE", "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM"
)}
try:
    os.environ["TWILIO_ACCOUNT_SID"] = "AC_test"
    os.environ["TWILIO_AUTH_TOKEN"] = "token"
    os.environ["TWILIO_FROM"] = "+15550000000"
    os.environ.pop("ANTICIPY_CHANNELS_MODE", None)
    assert TextChannel.configured() and CallChannel.configured()
    assert not TextChannel()._live() and not CallChannel()._live()
    os.environ["ANTICIPY_CHANNELS_MODE"] = "live"
    assert TextChannel()._live() and CallChannel()._live()
finally:
    for k, v in prev.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v

print("PASS channels: text/call real (mock mode, audited), readiness detected, app stubbed, TwiML escaped+bounded")
