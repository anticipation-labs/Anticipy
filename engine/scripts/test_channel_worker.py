"""ChannelWorker test — the REAL send_text/call worker on the frozen contract.

Pins:
  - send_text/call succeed in mock mode with truthy proof (the orchestrator's
    done-needs-proof law) and honest delivered=mock output
  - arg fallbacks (recipient/to, body/message/text) and the default-contact seam
  - a channel that does not send -> Result FAILED with no proof (a failed live
    send must never look delivered)
  - registered control-core-style (stub first, real worker last), the worker owns
    send_text/call while ChannelStub keeps send_email

Run:  PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_channel_worker.py
"""
import asyncio
import os

os.environ.pop("ANTICIPY_CHANNELS_MODE", None)   # mock: zero network

from anticipy_engine.core.bus import Bus  # noqa: E402
from anticipy_engine.core.envelopes import Job, JobStatus  # noqa: E402
from anticipy_engine.core.workers import ChannelStub, ChannelWorker  # noqa: E402


class DeadChannel:
    """A channel whose transport failed — what a live Twilio error returns."""
    name = "text"

    def send(self, to, message):
        return {"sent": False, "mock": False, "channel": self.name, "to": to,
                "message": message, "error": "boom"}


async def main():
    w = ChannelWorker(contact=lambda: "+10000000000")
    assert w.handles() == ["send_text", "call"]

    # mock send_text: success + truthy proof + honest mock labeling
    r = await w.handle(Job(intent="send_text", args={"recipient": "+15550001111", "body": "hi"}))
    assert r.status == JobStatus.success and r.proof, r
    assert r.proof["channel"] == "text" and r.proof["to"] == "+15550001111", r.proof
    assert r.proof["mock"] is True and r.proof["message_id"].startswith("mock-text-"), r.proof
    assert r.output["delivered"] == "mock", r.output
    assert w.text.sent and w.text.sent[-1]["message"] == "hi", "send must hit the audit log"

    # mock call: same contract over the call channel
    r = await w.handle(Job(intent="call", args={"to": "+15550001111", "message": "pickup at 3"}))
    assert r.status == JobStatus.success and r.proof["channel"] == "call", r
    assert w.call.sent and w.call.sent[-1]["message"] == "pickup at 3", w.call.sent

    # no recipient anywhere -> the default-contact seam answers
    r = await w.handle(Job(intent="send_text", args={"text": "fallback body"}))
    assert r.status == JobStatus.success and r.proof["to"] == "+10000000000", r.proof
    assert w.text.sent[-1]["message"] == "fallback body", w.text.sent[-1]

    # a channel that did not send -> FAILED, no proof (never fake a delivery)
    dead = ChannelWorker(text=DeadChannel(), contact="+10000000000")
    r = await dead.handle(Job(intent="send_text", args={"recipient": "x", "body": "y"}))
    assert r.status == JobStatus.failed and not r.proof and "boom" in (r.error or ""), r

    # control-core-style registration: real worker LAST owns send_text/call;
    # ChannelStub keeps send_email
    bus = Bus()
    stub = ChannelStub()
    bus.register_worker(stub)
    bus.register_worker(w)
    assert bus.worker_for("send_text") is w and bus.worker_for("call") is w
    assert bus.worker_for("send_email") is stub

    print("PASS channel_worker: real send_text/call (mock proof, audit), honest failure, "
          "stub keeps send_email")


if __name__ == "__main__":
    asyncio.run(main())
