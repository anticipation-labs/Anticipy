"""The onboarding scan TRIGGER — the wiring the 'scrapes you' step was missing.

The extension already handles a `discover_connections` message + POSTs results to /onboard/discover;
what was missing is the engine TELLING it to scan. This pins that BrowserLink.discover_connections
sends that exact message over the extension socket when connected, and safely no-ops (returns False,
never raises) when no extension is connected to drive.

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_onboard_scan.py
"""
import asyncio

from anticipy_engine.core.browser_link import BrowserLink


class FakeWS:
    def __init__(self):
        self.sent = []

    async def send_json(self, msg):
        self.sent.append(msg)


async def main():
    link = BrowserLink()

    # not connected -> safe no-op, never raises, never sends
    assert await link.discover_connections() is False, "no extension -> not triggered"

    # connected -> sends the exact discover_connections frame the extension listens for
    ws = FakeWS()
    await link.attach(ws)
    assert await link.discover_connections() is True
    assert ws.sent and ws.sent[-1]["type"] == "discover_connections", ws.sent
    assert ws.sent[-1]["services"] == [], "empty services -> extension uses its defaults"

    # a caller-supplied service list is passed through
    svcs = [{"name": "Gmail", "url": "https://mail.google.com"}]
    await link.discover_connections(svcs)
    assert ws.sent[-1]["services"] == svcs, ws.sent[-1]

    # diagnostic/proof mode waits for the extension's result payload
    scan_task = asyncio.create_task(link.scan_connections(svcs, timeout=1.0))
    await asyncio.sleep(0)
    assert ws.sent[-1]["type"] == "discover_connections" and ws.sent[-1]["job_id"].startswith("discover_")
    await link.on_message({
        "type": "result",
        "job_id": ws.sent[-1]["job_id"],
        "status": "success",
        "output": {"discovered": [{"service": "Gmail", "logged_in": True}], "count": 1, "posted": True},
    })
    scan = await scan_task
    assert scan["triggered"] is True and scan["posted"] is True, scan
    assert scan["discovered"][0]["service"] == "Gmail", scan

    # after the extension drops, the trigger no-ops again (no stale send)
    await link.detach(ws)
    before = len(ws.sent)
    assert await link.discover_connections() is False
    assert len(ws.sent) == before, "must not send to a detached socket"

    print("PASS onboard_scan: the engine can TRIGGER the Chrome account-scan over the extension "
          "socket (the missing 'scrapes you' wiring); safe no-op when nothing is connected")


if __name__ == "__main__":
    asyncio.run(main())
