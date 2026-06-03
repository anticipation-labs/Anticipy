"""Hard-site battery — runs EACH task N times (default 5) for consistency, judges
each, and prints a per-task success rate + failure reasons. General only; no
site-specific logic. Writes /tmp/anticipy_battery.txt.
Usage: _battery.py [round] [runs]
"""
import asyncio
import sys

import httpx

BASE = "http://127.0.0.1:8787"
ROUND = sys.argv[1] if len(sys.argv) > 1 else "1"
RUNS = int(sys.argv[2]) if len(sys.argv) > 2 else 5

BATTERY = [
    {"name": "Amazon: chair -> cart -> checkout (STOP)", "expect": "doable", "max": 28, "win_url": "checkout",
     "url": "https://www.amazon.com/s?k=gaming+chair",
     "task": "From the results pick a good-value, NON-SPONSORED gaming chair (low price + solid rating). Open it, click Add to Cart, then open the cart and Proceed to checkout to reach the checkout/sign-in page. STOP there — do NOT place the order or click Buy Now. action=answer with the chair name, price, and that you stopped at checkout."},
    {"name": "Google Flights: cheapest SFO->JFK", "expect": "doable", "max": 16,
     "url": "https://www.google.com/travel/flights?q=one-way%20flights%20from%20SFO%20to%20JFK",
     "task": "Find the price of the cheapest one-way flight shown from SFO to JFK. action=answer with the price (and airline if shown)."},
    {"name": "Form: fill + submit (httpbin)", "expect": "doable", "max": 18,
     "url": "https://httpbin.org/forms/post",
     "task": "Fill the form: Customer name 'Anticipy Test', telephone '5551234567', email 'test@anticipy.ai', size Medium, topping 'cheese', then click Submit order. action=answer confirming the form submitted (the next page shows the posted JSON)."},
    {"name": "GitHub: BrowserGym stars (read)", "expect": "doable", "max": 8,
     "url": "https://github.com/ServiceNow/BrowserGym",
     "task": "How many stars does this repository have? action=answer with the star count shown."},
    {"name": "YouTube: first ORGANIC video", "expect": "doable", "max": 10,
     "url": "https://www.youtube.com",
     "task": "Report the title of the first ORGANIC (non-sponsored, non-ad) video on the YouTube home page. action=answer with that title."},
    {"name": "reCAPTCHA demo (BLOCKED handoff)", "expect": "blocked", "max": 6,
     "url": "https://www.google.com/recaptcha/api2/demo",
     "task": "Submit this demo form. If a captcha or verification blocks you, stop and hand it back."},
]


async def wait(c, want, tries=520):
    for _ in range(tries):
        try:
            if (await c.get(BASE + "/ws/state")).json()["connected"] == want:
                return True
        except Exception:
            pass
        await asyncio.sleep(0.25)
    return False


def passed(t, oc):
    if t["expect"] == "blocked":
        return oc == "HANDOFF"
    return oc in ("SUCCESS", "STOPPED-SAFE")


def classify(t, r, judged):
    if r.get("stopped_for_safety"):
        return "STOPPED-SAFE"
    # robust oracle: a "reach checkout" task is satisfied if we landed on a checkout URL
    if t.get("win_url") and t["win_url"] in (r.get("final_url") or "").lower():
        return "SUCCESS"
    if r.get("needs_human"):
        return "HANDOFF"
    if t["expect"] == "blocked":
        a = (r.get("answer") or "").lower()
        return "HANDOFF" if ("hand" in a or "captcha" in a or "can't" in a or "cannot" in a) else "NO-HANDOFF"
    if r.get("exhausted"):
        return "EXHAUSTED"
    return "SUCCESS" if judged.get("success") else "FAIL"


async def main():
    lines = [f"==== BROWSER-HAND BATTERY — ROUND {ROUND}  ({RUNS} runs / task) ===="]
    async with httpx.AsyncClient(timeout=600) as c:
        for _ in range(60):
            try:
                if (await c.get(BASE + "/health")).status_code == 200:
                    break
            except Exception:
                pass
            await asyncio.sleep(0.25)
        if not await wait(c, True):
            print("FAIL: extension not connected")
            return

        summary = []
        for t in BATTERY:
            runs = []
            for n in range(RUNS):
                try:
                    r = (await c.post(BASE + "/agent/run",
                                      json={"task": t["task"], "start_url": t["url"], "max_steps": t["max"],
                                            "judge": t["expect"] == "doable"})).json()
                except Exception as e:
                    runs.append(("ERROR", {"reason": str(e)}, {}))
                    continue
                runs.append((classify(t, r, r.get("judgment", {})), r, r.get("judgment", {})))
            ok = sum(1 for oc, _, _ in runs if passed(t, oc))
            summary.append((t, ok, runs))
            lines.append(f"\n[{ok}/{RUNS}] {t['name']}  (expect {t['expect']})")
            for n, (oc, r, judged) in enumerate(runs):
                why = "" if passed(t, oc) else ("  | " + (r.get("reason") or judged.get("reason") or "")[:90])
                lines.append(f"   run{n + 1}: {oc:<12} steps={r.get('steps')} ans={(r.get('answer') or '')[:46]!r}{why}")

        lines.append(f"\n==== SCORECARD round {ROUND} ({RUNS} runs each) ====")
        for t, ok, _ in summary:
            bar = "PASS" if (ok >= 4 if t["expect"] == "doable" else ok == RUNS) else "----"
            lines.append(f"   {bar}  {ok}/{RUNS}  {t['name']}")

    report = "\n".join(lines)
    print(report)
    open("/tmp/anticipy_battery.txt", "w").write(report)


if __name__ == "__main__":
    asyncio.run(main())
