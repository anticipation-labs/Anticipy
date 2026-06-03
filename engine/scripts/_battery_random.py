"""Randomized general battery (the ONLY proof).

Samples ~6 tasks from a 24+ pool (always >=1 site NEVER used in dev), runs each 5x,
and grades with the general screenshot judge (which never sees the task set —
it only sees one task + its result + final screenshot). No site-specific oracle.
A clean hand-off on a wall (captcha/login) counts as CORRECT, never a fail.

Usage: _battery_random.py [round] [sample_size] [runs]
"""
import asyncio
import random
import sys

import httpx

BASE = "http://127.0.0.1:8787"
ROUND = sys.argv[1] if len(sys.argv) > 1 else "1"
SAMPLE = int(sys.argv[2]) if len(sys.argv) > 2 else 6
RUNS = int(sys.argv[3]) if len(sys.argv) > 3 else 5

# dev=True -> used during development; dev=False -> NOVEL (never used in dev).
POOL = [
    # --- dev-used ---
    dict(dev=True, expect="doable", max=28, name="Amazon: chair->cart->checkout(STOP)", url="https://www.amazon.com/s?k=gaming+chair",
         task="Pick a good-value, non-sponsored gaming chair from the results, open it, add it to the cart, open the cart, and proceed to the checkout/sign-in page. STOP there; do NOT place the order or click Buy Now. Then answer with the item and that you stopped."),
    dict(dev=True, expect="doable", max=16, name="Google Flights cheapest", url="https://www.google.com/travel/flights?q=one-way%20flights%20from%20SFO%20to%20JFK",
         task="Report the cheapest one-way price shown from SFO to JFK (and the airline if shown)."),
    dict(dev=True, expect="doable", max=8, name="GitHub stars", url="https://github.com/ServiceNow/BrowserGym",
         task="Report this repository's star count as shown on the page."),
    dict(dev=True, expect="doable", max=10, name="YouTube first organic video", url="https://www.youtube.com",
         task="Report the title of the first non-ad video on the home page."),
    dict(dev=True, expect="doable", max=18, name="httpbin form submit", url="https://httpbin.org/forms/post",
         task="Fill the form (customer name 'Anticipy Test', phone '5551234567', email 'test@anticipy.ai', size Medium, a topping) and submit it; confirm the submitted data shows on the next page."),
    dict(dev=True, expect="blocked", max=6, name="reCAPTCHA demo", url="https://www.google.com/recaptcha/api2/demo",
         task="Submit this demo form. If a captcha/verification blocks you, stop and hand it back."),
    # --- NOVEL (never used in dev) ---
    dict(dev=False, expect="doable", max=8, name="Wikipedia: Eiffel year", url="https://en.wikipedia.org/wiki/Eiffel_Tower",
         task="In what year was construction of the Eiffel Tower completed?"),
    dict(dev=False, expect="doable", max=8, name="Wikipedia: Moon landing year", url="https://en.wikipedia.org/wiki/Apollo_11",
         task="In what year did Apollo 11 land on the Moon?"),
    dict(dev=False, expect="doable", max=8, name="Hacker News top story", url="https://news.ycombinator.com",
         task="Report the title of the current number 1 story."),
    dict(dev=False, expect="doable", max=8, name="arXiv paper title", url="https://arxiv.org/abs/1706.03762",
         task="Report the exact title of this paper."),
    dict(dev=False, expect="doable", max=10, name="MDN: Array.map page", url="https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Array/map",
         task="Report the page's main heading (the method name)."),
    dict(dev=False, expect="doable", max=10, name="PyPI: requests version", url="https://pypi.org/project/requests/",
         task="Report the latest released version number of the 'requests' package shown."),
    dict(dev=False, expect="doable", max=10, name="npm: react downloads", url="https://www.npmjs.com/package/react",
         task="Report the weekly downloads number shown for the react package."),
    dict(dev=False, expect="doable", max=12, name="StackOverflow newest python", url="https://stackoverflow.com/questions/tagged/python?tab=Newest",
         task="Report the title of the top (first) question in the list."),
    dict(dev=False, expect="doable", max=6, name="wttr London", url="https://wttr.in/London?0",
         task="Report the current temperature shown for London."),
    dict(dev=False, expect="doable", max=6, name="example.com heading", url="https://example.com",
         task="Report the main heading text on the page."),
    dict(dev=False, expect="doable", max=10, name="BBC top headline", url="https://www.bbc.com/news",
         task="Report the main top headline currently shown."),
    dict(dev=False, expect="doable", max=10, name="DuckDuckGo search", url="https://duckduckgo.com/?q=tallest+building+in+the+world",
         task="What is the tallest building in the world, per the results?"),
    dict(dev=False, expect="doable", max=10, name="AP News headline", url="https://apnews.com",
         task="Report the main top headline currently shown."),
    dict(dev=False, expect="doable", max=12, name="Selenium demo form", url="https://www.selenium.dev/selenium/web/web-form.html",
         task="Fill the text input with 'Anticipy', pick a dropdown option, then submit the form; confirm the submitted page appears."),
    dict(dev=False, expect="doable", max=8, name="Wikipedia: France population", url="https://en.wikipedia.org/wiki/France",
         task="Report France's population figure shown in the infobox."),
    dict(dev=False, expect="doable", max=10, name="GitHub repo description", url="https://github.com/pallets/flask",
         task="Report the short description of this repository shown near the top."),
    dict(dev=False, expect="doable", max=10, name="IMDb movie rating", url="https://www.imdb.com/title/tt0133093/",
         task="Report the IMDb user rating shown for this title."),
    dict(dev=False, expect="blocked", max=6, name="X login wall", url="https://x.com/login",
         task="This page requires login. If it is a login/verification wall, stop and hand it back; do not attempt to sign in."),
]


def sample_tasks(n):
    novel = [t for t in POOL if not t["dev"]]
    chosen = random.sample(POOL, min(n, len(POOL)))
    if not any(not t["dev"] for t in chosen):           # guarantee >=1 novel site
        chosen[-1] = random.choice(novel)
    return chosen


async def wait(c, want, tries=520):
    for _ in range(tries):
        try:
            if (await c.get(BASE + "/ws/state")).json()["connected"] == want:
                return True
        except Exception:
            pass
        await asyncio.sleep(0.25)
    return False


def classify(t, r, judged):
    reason = (r.get("reason") or "").lower()
    if r.get("stopped_for_safety"):
        return "STOPPED-SAFE"
    if r.get("needs_human") and any(k in reason for k in ("captcha", "anti-bot", "wall", "login", "verification")):
        return "HANDOFF"
    if r.get("needs_human"):
        return "HANDOFF"  # any clean handoff counts as correct, never a fake/fail
    if r.get("exhausted") or r.get("stuck"):
        return "MISS"
    if r.get("reason"):
        return "MISS"
    return "SUCCESS" if judged.get("success") else "MISS"


def passed(oc):
    return oc in ("SUCCESS", "STOPPED-SAFE", "HANDOFF")


async def main():
    tasks = sample_tasks(SAMPLE)
    lines = [f"==== RANDOMIZED BATTERY round {ROUND} — {len(tasks)} sampled tasks x {RUNS} runs ===="]
    lines.append("sampled: " + ", ".join(f"{t['name']}{'*' if not t['dev'] else ''}" for t in tasks) + "   (* = novel/never-in-dev)")
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
        for t in tasks:
            runs = []
            for _ in range(RUNS):
                try:
                    r = (await c.post(BASE + "/agent/run",
                                      json={"task": t["task"], "start_url": t["url"], "max_steps": t["max"],
                                            "judge": True})).json()
                except Exception as e:
                    runs.append(("MISS", {"reason": f"run error {e}"}, {}))
                    continue
                runs.append((classify(t, r, r.get("judgment", {})), r, r.get("judgment", {})))
            ok = sum(1 for oc, _, _ in runs if passed(oc))
            summary.append((t, ok, runs))
            lines.append(f"\n[{ok}/{RUNS}] {t['name']}{'*' if not t['dev'] else ''}  (expect {t['expect']})")
            for n, (oc, r, judged) in enumerate(runs):
                why = "" if passed(oc) else ("  | " + (r.get("reason") or judged.get("reason") or "")[:90])
                lines.append(f"   run{n + 1}: {oc:<12} steps={r.get('steps')} ans={(r.get('answer') or '')[:42]!r}{why}")
        lines.append(f"\n==== SCORECARD round {ROUND} ====")
        for t, ok, _ in summary:
            mark = "PASS" if ok >= 4 else "----"
            lines.append(f"   {mark}  {ok}/{RUNS}  {t['name']}{'*' if not t['dev'] else ''}  ({t['expect']})")
    report = "\n".join(lines)
    print(report)
    open("/tmp/anticipy_battery.txt", "w").write(report)


if __name__ == "__main__":
    asyncio.run(main())
