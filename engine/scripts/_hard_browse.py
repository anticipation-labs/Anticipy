"""Hard-site browser-hand test: hot-reload to group-aware code, then drive several
hard sites through the 'Anticipy' tab group and report each result."""
import asyncio
import base64

import httpx

BASE = "http://127.0.0.1:8787"
SITES = [
    ("Amazon (heavy commerce SPA)", "https://www.amazon.com"),
    ("Google results (anti-bot/consent)", "https://www.google.com/search?q=anticipy+ai+wearable+pendant"),
    ("X — login wall", "https://x.com/login"),
]


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
    async with httpx.AsyncClient(timeout=45) as c:
        for _ in range(40):
            try:
                if (await c.get(BASE + "/health")).status_code == 200:
                    break
            except Exception:
                pass
            await asyncio.sleep(0.25)
        print("waiting for the extension to reconnect to the engine...")
        if not await wait_state(c, True):
            print("FAIL: extension not connected")
            return
        print("hot-reloading the extension to the group-aware code...")
        await c.post(BASE + "/ws/reload")
        await wait_state(c, False, tries=40)
        if not await wait_state(c, True):
            print("FAIL: no reconnect after reload")
            return
        print("reconnected.\n")

        saved = False
        for label, url in SITES:
            try:
                r = (await c.post(BASE + "/ws/browse", json={"intent": "browse_task", "args": {"url": url}})).json()
            except Exception as e:
                print(f"- {label}: ERROR {e}")
                continue
            p = r.get("proof") or {}
            out = r.get("output") or {}
            note = out.get("reason") or (out.get("text", "")[:70])
            print(f"- {label}")
            print(f"    status={r['status']}  title={p.get('title')!r}  group_id={out.get('group_id')}")
            print(f"    url={p.get('url')}  screenshot_bytes={len(p.get('screenshot',''))}")
            print(f"    note={note!r}")
            if not saved and p.get("screenshot", "").startswith("data:"):
                open("/tmp/anticipy_hard_proof.jpg", "wb").write(base64.b64decode(p["screenshot"].split(",", 1)[1]))
                saved = True
                print("    (saved screenshot -> /tmp/anticipy_hard_proof.jpg)")


if __name__ == "__main__":
    asyncio.run(main())
