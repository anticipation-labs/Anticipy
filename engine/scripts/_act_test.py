"""Piece 2 live test: observe + act. Hot-reload, observe example.com, click the
'More information' link, observe again to confirm navigation."""
import asyncio

import httpx

BASE = "http://127.0.0.1:8787"


async def wait_state(c, want, tries=80):
    for _ in range(tries):
        try:
            if (await c.get(BASE + "/ws/state")).json()["connected"] == want:
                return True
        except Exception:
            pass
        await asyncio.sleep(0.25)
    return False


async def main():
    async with httpx.AsyncClient(timeout=50) as c:
        for _ in range(40):
            try:
                if (await c.get(BASE + "/health")).status_code == 200:
                    break
            except Exception:
                pass
            await asyncio.sleep(0.25)
        if not await wait_state(c, True):
            print("FAIL: not connected"); return
        await c.post(BASE + "/ws/reload")
        await wait_state(c, False, 40)
        if not await wait_state(c, True):
            print("FAIL: no reconnect"); return

        o = (await c.post(BASE + "/ws/observe", json={"url": "https://example.com"})).json()
        out = o.get("output") or {}
        els = out.get("elements") or []
        print("OBSERVE example.com:", o["status"], "| url:", out.get("url"), "| #elements:", len(els))
        for e in els[:8]:
            print("   ", e)
        target = next((e for e in els if "more information" in (e.get("text") or "").lower()), els[0] if els else None)
        if not target:
            print("FAIL: no elements"); return
        print("CLICK idx", target["idx"], "->", target.get("text"))
        a = (await c.post(BASE + "/ws/act", json={"action": "click", "index": target["idx"]})).json()
        print("ACT:", a["status"], a.get("output"))

        o2 = (await c.post(BASE + "/ws/observe", json={})).json()
        out2 = o2.get("output") or {}
        print("AFTER CLICK -> url:", out2.get("url"), "| title:", out2.get("title"))


if __name__ == "__main__":
    asyncio.run(main())
