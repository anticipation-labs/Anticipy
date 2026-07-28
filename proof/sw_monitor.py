"""NOT-ME proof: attach CDP to the Anticipy extension service worker and log
every network request it makes (OpenRouter LLM calls + PocketBase job PATCHes)
with wall-clock timestamps. Writes JSONL to /home/ubuntu/anticipy_agent_decisions.jsonl.

Run: .venv/bin/python proof/sw_monitor.py
"""
import asyncio, json, time, datetime, sys
import requests, websockets

OUT = "/home/ubuntu/anticipy_agent_decisions.jsonl"
PORT = 29229

def now():
    return datetime.datetime.utcnow().strftime("%H:%M:%S.%f")[:-3] + "Z"

def log(rec):
    rec["ts"] = now()
    with open(OUT, "a") as f:
        f.write(json.dumps(rec) + "\n")
    print(rec["ts"], rec.get("kind"), str(rec.get("summary"))[:140], flush=True)

async def main():
    targets = requests.get(f"http://127.0.0.1:{PORT}/json").json()
    sw = next(t for t in targets if t["type"] == "service_worker" and "kbcjggme" in t["url"])
    async with websockets.connect(sw["webSocketDebuggerUrl"], max_size=50*1024*1024) as ws:
        mid = 0
        async def send(method, params=None):
            nonlocal mid
            mid += 1
            await ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
            return mid
        await send("Network.enable")
        log({"kind": "monitor", "summary": "attached to service worker, Network enabled"})
        reqs = {}
        while True:
            msg = json.loads(await ws.recv())
            m = msg.get("method")
            p = msg.get("params", {})
            if m == "Network.requestWillBeSent":
                url = p["request"]["url"]
                reqs[p["requestId"]] = url
                if "openrouter" in url:
                    body = p["request"].get("postData", "")
                    goal = ""
                    try:
                        j = json.loads(body)
                        goal = (j["messages"][-1]["content"] or "")[:200]
                    except Exception:
                        goal = body[:200]
                    log({"kind": "llm_request", "summary": goal, "url": url})
                elif "8090" in url and p["request"]["method"] in ("PATCH", "POST"):
                    log({"kind": "backend_write", "summary": f'{p["request"]["method"]} {url.split("records")[-1]} {p["request"].get("postData","")[:200]}'})
            elif m == "Network.loadingFinished":
                rid = p["requestId"]
                url = reqs.get(rid, "")
                if "openrouter" in url:
                    i = await send("Network.getResponseBody", {"requestId": rid})
                    # collect response
                    while True:
                        r2 = json.loads(await ws.recv())
                        if r2.get("id") == i:
                            try:
                                body = r2["result"]["body"]
                                j = json.loads(body)
                                content = j["choices"][0]["message"]["content"]
                                log({"kind": "llm_decision", "summary": content[:300]})
                            except Exception as e:
                                log({"kind": "llm_decision", "summary": f"(unparsed) {e}"})
                            break
                        else:
                            # re-dispatch events we swallowed
                            m2 = r2.get("method")
                            if m2 == "Network.requestWillBeSent":
                                reqs[r2["params"]["requestId"]] = r2["params"]["request"]["url"]

asyncio.run(main())
