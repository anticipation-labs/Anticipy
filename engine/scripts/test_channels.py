"""Room 10 test: channels seam — call / text / app, all stubbed (no real send).

Run:  PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_channels.py
"""
from anticipy_engine.channels import Channels
from anticipy_engine.channels.base import Channel

ch = Channels()

for c, to in [(ch.call, "+15551234567"), (ch.text, "+15551234567"), (ch.app, "device")]:
    assert isinstance(c, Channel)
    out = c.send(to, "your 3pm moved")
    assert out["sent"] is False and out["stub"] is True
    assert out["channel"] == c.name and out["to"] == to

assert {ch.call.name, ch.text.name, ch.app.name} == {"call", "text", "app"}

print("PASS room 10: channels seam (call / text / app — stubbed, no real send)")
print("  channels:", [ch.call.name, ch.text.name, ch.app.name])
