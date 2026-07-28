import json, requests, asyncio, websockets

ts = requests.get("http://localhost:29229/json").json()
sw = next(t for t in ts if t["type"] == "service_worker" and "kbcjggme" in t["url"])
expr = """
(async () => {
  const tab = await chrome.tabs.create({url:"https://duckduckgo.com/", active:false});
  await new Promise(r=>setTimeout(r,5000));
  try {
    await chrome.scripting.executeScript({target:{tabId:tab.id}, files:["page_map.js"]});
    const [{result}] = await chrome.scripting.executeScript({target:{tabId:tab.id}, func:()=>window.__anticipyMapPage()});
    return JSON.stringify({ok:true, url:result.url, n:(result.elements||[]).length}).slice(0,300);
  } catch(e) { return "ERR: "+String(e); }
})()
"""

async def go():
    async with websockets.connect(sw["webSocketDebuggerUrl"], max_size=None) as ws:
        await ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                                  "params": {"expression": expr, "awaitPromise": True, "returnByValue": True}}))
        while True:
            r = json.loads(await ws.recv())
            if r.get("id") == 1:
                print(json.dumps(r["result"], indent=1)[:600], flush=True)
                break

asyncio.run(go())
