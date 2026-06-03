"""Piece 3 (integration): drive the real BrowserHand over the real WS, with a
simulated extension. Usage: <base_http_url>."""
import asyncio
import json
import sys

import httpx
import websockets

BASE = sys.argv[1].rstrip("/")
WS = BASE.replace("http", "ws") + "/ws/extension"


async def extension(ws, behavior):
    async for raw in ws:
        msg = json.loads(raw)
        if msg.get("type") == "browse_job":
            jid = msg["job_id"]
            if behavior == "login_wall":
                await ws.send(json.dumps({"type": "result", "job_id": jid, "status": "needs_human",
                                          "output": {"reason": "please sign in"}, "proof": None}))
            else:
                await ws.send(json.dumps({"type": "result", "job_id": jid, "status": "success",
                                          "proof": {"screenshot": "data:image/png;base64,iVBOR", "id": "page-1"},
                                          "output": {"title": "Example Domain"}}))


async def wait_connected(client, want, tries=25):
    for _ in range(tries):
        st = (await client.get(BASE + "/ws/state")).json()
        if st.get("connected") == want:
            return True
        await asyncio.sleep(0.2)
    return False


async def main():
    token = httpx.get(BASE + "/ws/token", timeout=5).json()["token"]

    # success: extension connected, executes, returns screenshot proof
    async with websockets.connect(WS + "?token=" + token, open_timeout=5) as ws:
        task = asyncio.create_task(extension(ws, "success"))
        async with httpx.AsyncClient(timeout=15) as c:
            assert await wait_connected(c, True)
            res = (await c.post(BASE + "/ws/browse",
                                json={"intent": "browse_task", "args": {"task": "open https://example.com"}})).json()
        assert res["status"] == "success" and res["proof"].get("screenshot"), res
        task.cancel()

    # disconnected: no extension -> clean needs_human, no hang
    async with httpx.AsyncClient(timeout=15) as c:
        assert await wait_connected(c, False)
        res = (await c.post(BASE + "/ws/browse", json={"intent": "browse_task", "args": {}})).json()
    assert res["status"] == "needs_human" and "isn't connected" in str(res.get("output")), res

    # login-wall: extension reports needs_human -> not a fake success
    async with websockets.connect(WS + "?token=" + token, open_timeout=5) as ws:
        task = asyncio.create_task(extension(ws, "login_wall"))
        async with httpx.AsyncClient(timeout=15) as c:
            assert await wait_connected(c, True)
            res = (await c.post(BASE + "/ws/browse", json={"intent": "browse_task", "args": {}})).json()
        assert res["status"] == "needs_human" and "sign in" in str(res.get("output")), res
        task.cancel()

    print("PASS piece 3 (integration): browse over real WS — success+screenshot; disconnected->needs_human; login-wall->needs_human")


if __name__ == "__main__":
    asyncio.run(main())
