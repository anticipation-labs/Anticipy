"""Integrated hands DONE-TEST driver (headless portion). A goal runs end to end
through the REAL hands: API hand (mock) for an email step; the no-Arcade-tool
post_to_x reroutes to the browser hand (real WS, simulated extension). Asserts
verify-before-done, glass-box trail, scorecard, and smart-model-used-twice.
Usage: <base_http_url>."""
import asyncio
import json
import sys

import httpx
import websockets

BASE = sys.argv[1].rstrip("/")
WS = BASE.replace("http", "ws") + "/ws/extension"
EVENT = "Draft the Q3 deck for Sarah and check the launch page on the website."


async def extension(ws):
    async for raw in ws:
        m = json.loads(raw)
        if m.get("type") == "browse_job":
            await ws.send(json.dumps({"type": "result", "job_id": m["job_id"], "status": "success",
                                      "proof": {"screenshot": "data:image/png;base64,iVBOR", "id": "x-post-1"},
                                      "output": {"posted": True}}))


async def wait_connected(c, want=True, tries=25):
    for _ in range(tries):
        if (await c.get(BASE + "/ws/state")).json().get("connected") == want:
            return True
        await asyncio.sleep(0.2)
    return False


async def main():
    token = httpx.get(BASE + "/ws/token", timeout=5).json()["token"]
    async with websockets.connect(WS + "?token=" + token, open_timeout=5) as ws:
        task = asyncio.create_task(extension(ws))
        async with httpx.AsyncClient(timeout=30) as c:
            assert await wait_connected(c, True)
            ev = (await c.post(BASE + "/event", json={"text": EVENT, "source": "app"})).json()
            assert ev["decision"] == "act" and ev["goal_id"], ev   # act-first: safe -> just do it
            goal = (await c.get(BASE + f"/goals/{ev['goal_id']}")).json()
            sc = (await c.get(BASE + "/scorecard")).json()
            gw = (await c.get(BASE + "/gateway")).json()
            gb = (await c.get(BASE + "/glassbox?limit=80")).json()["entries"]
        task.cancel()

    assert goal["state"] == "done", goal["state"]
    steps = {s["intent"]: s for s in goal["steps"]}
    assert "send_email" in steps and "post_to_x" in steps, list(steps)

    se = steps["send_email"]
    assert se["state"] == "done" and se["result"]["proof"]["id"].startswith("mock-"), se  # API hand (mock)

    px = steps["post_to_x"]
    assert px["state"] == "done" and px["result"]["proof"].get("screenshot"), px  # rerouted to browser hand

    # verify-before-done: no step is done without proof
    for s in goal["steps"]:
        assert not (s["state"] == "done" and not (s.get("result") and s["result"].get("proof"))), s

    assert gw["smart_calls"] == 1, gw                       # act-first: plan only (harm-line is deterministic)
    assert sc["goal_outcomes"].get("success", 0) >= 1, sc
    kinds = {e["kind"] for e in gb}
    for need in ("event", "decision", "job", "result", "goal_done", "reroute"):
        assert need in kinds, (need, sorted(kinds))

    print("PASS hands DONE-TEST (integrated, headless):")
    print("  send_email -> API hand (mock) proof id:", se["result"]["proof"]["id"])
    print("  post_to_x  -> no Arcade tool -> rerouted to browser hand; screenshot proof:",
          bool(px["result"]["proof"].get("screenshot")))
    print("  smart_calls:", gw["smart_calls"], "| scorecard:", sc)
    print("  glassbox kinds:", sorted(kinds))


if __name__ == "__main__":
    asyncio.run(main())
