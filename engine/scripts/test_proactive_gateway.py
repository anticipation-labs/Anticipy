"""Plan Baby Steps gateway integration smoke test.

Run:
  PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_proactive_gateway.py
"""
from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

os.environ.setdefault("ANTICIPY_MODEL_PROVIDER", "stub")
os.environ.setdefault("ANTICIPY_HANDS_MODE", "mock")
os.environ.setdefault("ANTICIPY_NATIVE_BRIDGE_FALLBACK", "0")
os.environ.setdefault("ANTICIPY_TICK_SECONDS", "0")
os.environ.setdefault("ANTICIPY_INBOUND_POLL_SECONDS", "0")

from anticipy_engine.core.control_core import ControlCore  # noqa: E402


async def main() -> None:
    data_dir = Path(tempfile.mkdtemp(prefix="anticipy-gateway-"))
    core = ControlCore(data_dir=data_dir)
    await core.start()
    try:
        out = await core.owner_ingest(
            "phase_zero_text",
            "Please remind me to call Maya tomorrow morning.",
            {"ui": "gateway_test"},
            execute_actions=True,
        )
        assert "gateway_event" in out, out
        event = out["gateway_event"]
        assert event["event_id"], event
        assert event["source"] == "app", event
        assert event["source_label"] == "phase_zero_text", event
        assert "structured_summary" in event, event
        assert "ST-NO-FAKE-DONE" in event["source_of_truth_tags"], event

        recent = core.proactive_gateway_recent(limit=5)
        assert recent["count"] >= 1, recent
        assert recent["events"][0]["event_id"] == event["event_id"], recent

        cards = core.owner_cards(limit=10)["cards"]
        assert cards, out
        assert any(c.get("gateway_event_id") == event["event_id"] for c in cards), cards

        core.gateway_ledger.record_browser_result(
            ask_id="browser-card-1",
            task="Find return instructions",
            success=True,
            answer="Return instructions found.",
            url="https://example.com/returns",
            screenshot=False,
            source_event_id=event["event_id"],
        )
        browser_recent = core.proactive_gateway_recent(limit=2)["events"][0]
        assert browser_recent["source"] == "browser", browser_recent
        assert browser_recent["browser_run"]["answer"] == "Return instructions found.", browser_recent

        core.gateway_ledger.record_listen_status(
            source="mac_mic",
            listening=True,
            details={"device": "2", "window_seconds": 8.0},
        )
        core.gateway_ledger.record_listen_status(
            source="mac_mic",
            listening=False,
            details={"windows": 0, "utterances": 0},
        )
        listen_events = core.proactive_gateway_recent(limit=2)["events"]
        assert listen_events[0]["status"] == "stopped", listen_events
        assert listen_events[1]["status"] == "listening", listen_events
        assert listen_events[0]["source"] == "mic", listen_events
        assert "ST-ACTIVE-LISTENING" in listen_events[0]["source_of_truth_tags"], listen_events
    finally:
        await core.stop()


if __name__ == "__main__":
    asyncio.run(main())
    print("proactive gateway: ok")
