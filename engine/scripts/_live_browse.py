"""Live browser-hand proof: hot-reload the loaded extension, then drive a real
browse on a benign page and report the screenshot proof. Usage: [base] [url]."""
import asyncio
import sys

import httpx

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8787").rstrip("/")
URL = sys.argv[2] if len(sys.argv) > 2 else "https://example.com"


async def main():
    async with httpx.AsyncClient(timeout=30) as c:
        print("triggering hot-reload...")
        await c.post(BASE + "/ws/reload")
        for _ in range(20):  # observe the disconnect
            if not (await c.get(BASE + "/ws/state")).json()["connected"]:
                break
            await asyncio.sleep(0.25)
        ok = False
        for _ in range(60):  # wait for reconnect with the new code
            if (await c.get(BASE + "/ws/state")).json()["connected"]:
                ok = True
                break
            await asyncio.sleep(0.25)
        print("reconnected:", ok)
        if not ok:
            print("FAIL: extension did not reconnect after reload")
            return

        print(f"browsing {URL} ...")
        r = (await c.post(BASE + "/ws/browse",
                          json={"intent": "browse_task", "args": {"url": URL}})).json()
        p = r.get("proof") or {}
        print("status:", r["status"])
        print("page url:", p.get("url"))
        print("page title:", p.get("title"))
        print("screenshot bytes:", len(p.get("screenshot", "")))
        print("output:", r.get("output"))


if __name__ == "__main__":
    asyncio.run(main())
