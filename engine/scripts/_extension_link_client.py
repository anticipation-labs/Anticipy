"""Simulated-extension WS client for the piece 2 test. Usage: <base_http_url>."""
import asyncio
import json
import sys

import httpx
import websockets

BASE = sys.argv[1].rstrip("/")
WS = BASE.replace("http", "ws") + "/ws/extension"


async def main():
    token = httpx.get(BASE + "/ws/token", timeout=5).json()["token"]

    # 1) unauthenticated connect -> rejected at the handshake
    rejected = False
    try:
        async with websockets.connect(WS, open_timeout=5) as ws:
            await ws.send(json.dumps({"type": "ping"}))
            await asyncio.wait_for(ws.recv(), timeout=3)
    except Exception:
        rejected = True
    assert rejected, "unauthenticated WS connect must be rejected"

    # 2) authenticated connect -> ping/pong, keepalive persistence, reload broadcast
    async with websockets.connect(WS + "?token=" + token, open_timeout=5) as ws:
        await ws.send(json.dumps({"type": "ping"}))
        assert json.loads(await asyncio.wait_for(ws.recv(), timeout=3))["type"] == "pong"

        for _ in range(3):  # keepalive: pings over a few seconds, link stays open
            await asyncio.sleep(1)
            await ws.send(json.dumps({"type": "ping"}))
            assert json.loads(await asyncio.wait_for(ws.recv(), timeout=3))["type"] == "pong"

        httpx.post(BASE + "/ws/reload", timeout=5)  # dev hot-reload path
        got_reload = False
        for _ in range(6):
            m = json.loads(await asyncio.wait_for(ws.recv(), timeout=3))
            if m.get("type") == "reload":
                got_reload = True
                break
        assert got_reload, "expected reload broadcast over the WS"

    print("PASS piece 2: extension link (token-auth WS, ping/pong keepalive, reject unauth, reload)")


if __name__ == "__main__":
    asyncio.run(main())
