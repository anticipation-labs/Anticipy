import json, requests, asyncio, websockets

ts = requests.get("http://localhost:29229/json").json()
sw = next(t for t in ts if t["type"] == "service_worker" and "kbcjggme" in t["url"])

async def go():
    async with websockets.connect(sw["webSocketDebuggerUrl"], max_size=None) as ws:
        await ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                                  "params": {"expression": "chrome.runtime.reload()"}}))
        await ws.recv()
        print("reloaded", flush=True)

asyncio.run(go())
