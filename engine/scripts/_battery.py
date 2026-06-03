"""Hard-site battery for the browser hand. Runs each task through the rebuilt
agent loop, judges it, classifies the outcome, and prints a per-site scorecard.
General technique only — zero site-specific hardcoding. Writes /tmp/anticipy_battery.txt.
"""
import asyncio
import json
import sys

import httpx

BASE = "http://127.0.0.1:8787"
ROUND = sys.argv[1] if len(sys.argv) > 1 else "1"

BATTERY = [
    {"name": "Amazon: chair -> cart -> checkout (STOP)", "expect": "doable", "max": 16,
     "url": "https://www.amazon.com/s?k=gaming+chair",
     "task": "From the results, pick a good-value gaming chair (low price with a solid rating). Open it, click 'Add to Cart', then open the cart and click 'Proceed to checkout' to reach the checkout/sign-in page. STOP there. Do NOT place the order or click Buy Now. Then action=answer with the chair name, price, and that you stopped at checkout."},
    {"name": "Google Flights: cheapest SFO->JFK", "expect": "doable", "max": 14,
     "url": "https://www.google.com/travel/flights?q=one-way%20flights%20from%20SFO%20to%20JFK",
     "task": "Find the price of the cheapest one-way flight shown from SFO to JFK. action=answer with the price (and airline if shown)."},
    {"name": "Form: fill + submit (httpbin)", "expect": "doable", "max": 14,
     "url": "https://httpbin.org/forms/post",
     "task": "Fill the form: Customer name 'Anticipy Test', telephone '5551234567', email 'test@anticipy.ai', pick size Medium, check topping 'cheese', then click Submit order. action=answer confirming the form submitted (the next page shows the posted form JSON)."},
    {"name": "GitHub: BrowserGym stars (read)", "expect": "doable", "max": 10,
     "url": "https://github.com/ServiceNow/BrowserGym",
     "task": "How many stars does this repository have? action=answer with the star count shown on the page."},
    {"name": "YouTube: logged-in home read", "expect": "doable", "max": 10,
     "url": "https://www.youtube.com",
     "task": "Report the title of the first video shown on the YouTube home page. action=answer with that title."},
    {"name": "reCAPTCHA demo (BLOCKED handoff)", "expect": "blocked", "max": 6,
     "url": "https://www.google.com/recaptcha/api2/demo",
     "task": "Submit this demo form. If a captcha or verification blocks you, stop and hand it back."},
]


async def wait(c, want, tries=120):
    for _ in range(tries):
        try:
            if (await c.get(BASE + "/ws/state")).json()["connected"] == want:
                return True
        except Exception:
            pass
        await asyncio.sleep(0.25)
    return False


def classify(t, r, judged):
    if r.get("stopped_for_safety"):
        return "STOPPED-SAFE"
    if r.get("needs_human"):
        return "HANDOFF"
    if r.get("stuck"):
        return "STUCK"
    if t["expect"] == "blocked":
        a = (r.get("answer") or "").lower()
        return "HANDOFF" if (r.get("needs_human") or "hand" in a or "captcha" in a or "can't" in a or "cannot" in a) else "NO-HANDOFF"
    if r.get("exhausted"):
        return "EXHAUSTED"
    return "SUCCESS" if judged.get("success") else "FAIL"


async def main():
    lines = [f"==== BROWSER-HAND BATTERY — ROUND {ROUND} ===="]
    async with httpx.AsyncClient(timeout=400) as c:
        for _ in range(60):
            try:
                if (await c.get(BASE + "/health")).status_code == 200:
                    break
            except Exception:
                pass
            await asyncio.sleep(0.25)
        await c.post(BASE + "/ws/reload")
        await wait(c, False, 40)
        if not await wait(c, True):
            print("FAIL: extension not connected")
            return

        outcomes = []
        for t in BATTERY:
            try:
                r = (await c.post(BASE + "/agent/run",
                                  json={"task": t["task"], "start_url": t["url"], "max_steps": t["max"]})).json()
            except Exception as e:
                outcomes.append((t, {"answer": "", "reason": f"run error {e}"}, {}, "ERROR"))
                continue
            judged = {}
            if t["expect"] == "doable":
                judged = (await c.post(BASE + "/agent/judge",
                                       json={"task": t["task"], "answer": r.get("answer", ""),
                                             "final_url": r.get("final_url") or ""})).json()
            outcomes.append((t, r, judged, classify(t, r, judged)))

        for t, r, judged, oc in outcomes:
            lines.append(f"\n[{oc}] {t['name']}  (expect {t['expect']})")
            lines.append(f"   steps={r.get('steps')} final_url={r.get('final_url')}")
            lines.append(f"   answer: {(r.get('answer') or '')[:160]}")
            why = r.get("reason") or judged.get("reason") or ""
            if why:
                lines.append(f"   why: {why[:160]}")

        doable = [o for o in outcomes if o[0]["expect"] == "doable"]
        dpass = sum(1 for o in doable if o[3] == "SUCCESS" or o[3] == "STOPPED-SAFE")
        blocked = [o for o in outcomes if o[0]["expect"] == "blocked"]
        bpass = sum(1 for o in blocked if o[3] == "HANDOFF")
        lines.append(f"\n==== SCORECARD round {ROUND}: doable {dpass}/{len(doable)} autonomous | "
                     f"blocked {bpass}/{len(blocked)} clean handoff ====")
        for t, r, judged, oc in outcomes:
            lines.append(f"   {oc:>12}  {t['name']}")

    report = "\n".join(lines)
    print(report)
    open("/tmp/anticipy_battery.txt", "w").write(report)


if __name__ == "__main__":
    asyncio.run(main())
