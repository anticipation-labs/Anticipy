"""Piece 2 test: the worker contract + scriptable stubs.

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_workers.py
"""
import asyncio

from anticipy_engine.core.envelopes import Job, JobStatus
from anticipy_engine.core.worker import Worker
from anticipy_engine.core.workers import (
    BrowserStub, ChannelStub, ConnectorStub, MemoryStub,
    FAIL, NEEDS_HUMAN, SUCCESS, SUCCESS_NO_PROOF,
)


async def main() -> None:
    channel, memory, connector, browser = ChannelStub(), MemoryStub(), ConnectorStub(), BrowserStub()
    for w in (channel, memory, connector, browser):
        assert isinstance(w, Worker)

    # registered intents
    assert "send_email" in channel.handles()
    assert set(memory.handles()) == {"read_context", "write_memory"}
    assert "create_event" in connector.handles()
    assert browser.handles() == ["browse_task"]

    # success carries proof
    r = await channel.handle(Job(intent="send_email", args={"to": "Sarah"}))
    assert r.status == JobStatus.success and r.proof and "message_id" in r.proof

    # read_context returns canned context
    rc = await memory.handle(Job(intent="read_context"))
    assert rc.status == JobStatus.success and "context" in rc.output

    # fail-once-then-succeed
    connector.script("create_event", FAIL, SUCCESS)
    first = await connector.handle(Job(intent="create_event"))
    second = await connector.handle(Job(intent="create_event"))
    assert first.status == JobStatus.failed and first.proof is None
    assert second.status == JobStatus.success and second.proof and "record_id" in second.proof

    # needs_human
    browser.script("browse_task", NEEDS_HUMAN)
    nh = await browser.handle(Job(intent="browse_task"))
    assert nh.status == JobStatus.needs_human and nh.proof is None

    # success WITHOUT proof (contract violation we can detect downstream)
    channel.script("send_text", SUCCESS_NO_PROOF)
    np = await channel.handle(Job(intent="send_text"))
    assert np.status == JobStatus.success and np.proof is None

    print("PASS piece 2: worker contract + scriptable stubs")
    print("  channel proof:", r.proof)
    print("  connector retry:", first.status.value, "->", second.status.value)


if __name__ == "__main__":
    asyncio.run(main())
