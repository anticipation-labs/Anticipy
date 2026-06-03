"""A small WebVoyager-style slice: run live tasks through the real agent loop and
judge each. Prints a first real success rate. Usage: just run (engine on :8787)."""
import asyncio

import httpx

BASE = "http://127.0.0.1:8787"
TASKS = [
    {"name": "arXiv abstract (read)", "start_url": "https://arxiv.org/abs/2401.13919",
     "task": "What is the exact title of this paper?"},
    {"name": "Wikipedia fact (read)", "start_url": "https://en.wikipedia.org/wiki/Eiffel_Tower",
     "task": "In what year was construction of the Eiffel Tower completed?"},
    {"name": "example -> IANA (click-through)", "start_url": "https://example.com",
     "task": "Click through from this page to find which organization manages the example domains, and name it."},
    {"name": "Hacker News (dynamic read)", "start_url": "https://news.ycombinator.com",
     "task": "What is the title of the current number 1 top story?"},
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
    async with httpx.AsyncClient(timeout=220) as c:
        for _ in range(40):
            try:
                if (await c.get(BASE + "/health")).status_code == 200:
                    break
            except Exception:
                pass
            await asyncio.sleep(0.25)
        await c.post(BASE + "/ws/reload")
        await wait_state(c, False, 40)
        if not await wait_state(c, True):
            print("FAIL: extension not connected")
            return

        results = []
        for t in TASKS:
            print(f"\n=== {t['name']} ===")
            print(f"  TASK: {t['task']}")
            try:
                r = (await c.post(BASE + "/agent/run",
                                  json={"task": t["task"], "start_url": t["start_url"], "max_steps": 8})).json()
            except Exception as e:
                print("  RUN ERROR:", e)
                results.append((t["name"], False))
                continue
            ans, steps, furl = r.get("answer", ""), r.get("steps"), r.get("final_url")
            j = (await c.post(BASE + "/agent/judge",
                              json={"task": t["task"], "answer": ans, "final_url": furl or ""})).json()
            ok = j.get("success")
            print(f"  steps={steps}  final_url={furl}")
            print(f"  answer: {(ans or '')[:200]}")
            print(f"  judge: {'PASS' if ok else 'FAIL'} — {(j.get('reason') or '')[:160]}")
            results.append((t["name"], ok))

        passed = sum(1 for _, o in results if o)
        print(f"\n==== WebVoyager slice: {passed}/{len(results)} passed ====")
        for n, o in results:
            print(f"   {'PASS' if o else 'FAIL'}  {n}")


if __name__ == "__main__":
    asyncio.run(main())
