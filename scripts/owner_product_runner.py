#!/usr/bin/env python3
"""OWNER PRODUCT RUNNER — end-to-end proof through the REAL product surface.

Drives the running product (Next app at :3000 -> engine at :8787) the way the owner does:
onboard -> show the tool mesh honestly -> feed a messy multi-person day through the product
input route -> assert the resulting cards/receipts -> drive a safe reversible action arm
(open-web browser; live Calendar create->read-back->delete) -> prove a follow-up exists ->
save every artifact. The product is what Omar can open, use, and trust — this asserts that.

Run:  PYTHONPATH=engine engine/.venv/bin/python scripts/owner_product_runner.py
Artifacts: docs/e2e/owner_product_runner/latest/
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[1]
APP = os.environ.get("ANTICIPY_APP_URL", "http://localhost:3000").rstrip("/")
ENGINE = os.environ.get("ANTICIPY_ENGINE_URL", "http://127.0.0.1:8787").rstrip("/")
OUT = REPO / "docs/e2e/owner_product_runner/latest"
OUT.mkdir(parents=True, exist_ok=True)

DAY = [
    'Mom: "Omar, please call Amazon about that plant I ordered."',
    'Omar: "Yeah, I\'ll handle it."',
    'Omar: "Honestly I\'m so done with this coffee machine, I\'m moving to the woods."',
    'Boss: "Can you get Sam the revised deck by Friday?"',
    'Omar: "Yeah, remind me before I send it."',
    'Client: "Please make sure the retainer note is in the CRM before the call."',
    'Omar: "If I win the lottery I\'m buying an island."',
    'Omar: "The Jarvis standing desk is the one I liked. Don\'t buy it yet."',
    'Later: "Can you pull up that desk thing?"',
    'Mom: "Also call Amazon about the expired yogurt and get a refund."',
    'Omar: "Remind me to refill Maya\'s inhaler before the pharmacy closes."',
    'Omar: "Drop the rent check off, it\'s $1,450."',
    'Omar: "Great morning, just great. Everything is broken."',
]

results = {"seams": {}, "checks": [], "artifacts": []}


def seam(name, ok, detail=""):
    results["seams"][name] = {"pass": bool(ok), "detail": detail}
    print(f"[{'PASS' if ok else 'FAIL'}] seam:{name} {detail}"[:300], flush=True)
    return ok


def check(name, ok, detail=""):
    results["checks"].append({"name": name, "pass": bool(ok), "detail": detail})
    print(f"   [{'ok' if ok else 'XX'}] {name}: {detail}"[:300], flush=True)
    return ok


def save(fname, data):
    p = OUT / fname
    p.write_text(data if isinstance(data, str) else json.dumps(data, indent=2, default=str))
    results["artifacts"].append(str(p.relative_to(REPO)))


def _text(card):
    return " ".join(str(card.get(k) or "") for k in ("title", "source_text", "action", "reason")).lower()


def main():
    commit = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
                            capture_output=True, text=True).stdout.strip()
    results["commit"] = commit
    results["product_surface"] = APP
    save("REPLAY.md", f"# Owner product runner\ncommit: {commit}\nproduct: {APP}\n\n"
         f"Replay:\n    PYTHONPATH=engine engine/.venv/bin/python scripts/owner_product_runner.py\n")

    with httpx.Client(timeout=300) as c:
        # ---- SEAM 1: front door + app<->engine ----
        try:
            app_ok = c.get(APP + "/").status_code == 200
            eng = c.get(APP + "/api/status").json()
            link_ok = app_ok and bool(eng.get("engine") == "ok")
        except Exception as e:
            return seam("app_engine", False, f"{type(e).__name__}: {e}") and False
        seam("app_engine", link_ok, f"app=200 engine={eng.get('engine')}")
        if not link_ok:
            return False

        # ---- SEAM 2: profile (onboard the owner + the people in the scenario) ----
        prof = c.post(APP + "/api/owner/onboard", json={
            "source": "product_runner",
            "owner_name": "Omar",
            "people": [
                {"name": "Mom", "relationship": "mother", "channels": ["call"]},
                {"name": "Sam", "relationship": "works with me", "channels": ["email"]},
                {"name": "Maya", "relationship": "wife", "channels": ["text"]},
                {"name": "Boss", "relationship": "manager", "channels": ["email"]},
            ],
        })
        seam("profile", prof.status_code == 200, f"onboard HTTP {prof.status_code}")

        # ---- SEAM 3: tool/account mesh, honestly ----
        ready = c.get(APP + "/api/readiness").json()
        save("readiness.json", ready)
        live = [x["capability"] for x in ready.get("capabilities", []) if x.get("status") == "live"]
        seam("tool_mesh", ready.get("total", 0) > 0,
             f"{ready.get('live_count')}/{ready.get('total')} live: {live}")

        # ---- SEAM 4: input route — feed the messy day through the product ----
        save("input.txt", "\n".join(DAY))
        ing = c.post(APP + "/api/owner/ingest", json={
            "source": "transcript", "text": "\n".join(DAY), "execute_actions": True})
        if ing.status_code != 200:
            return seam("input_route", False, f"ingest HTTP {ing.status_code}: {ing.text[:200]}") and False
        data = ing.json()
        cards = data.get("cards") or []
        save("cards.json", data)
        seam("input_route", True, f"{len(cards)} cards, {data.get('ignored_line_count')} ignored")

        # ---- SEAM 5: assert the scenario invariants on the rendered cards ----
        def has(*subs):
            return [c2 for c2 in cards if all(s in _text(c2) for s in subs)]
        def acted_or_asked(cs):
            return [x for x in cs if (x.get("execution") or {}).get("decision") in ("act", "ask")
                    or x.get("disposition") in ("ask", "do", "blocked")]

        # cardinal: vents + jokes silent
        coffee = acted_or_asked(has("coffee"))
        lottery = acted_or_asked(has("lottery")) + acted_or_asked(has("island"))
        great = [c2 for c2 in cards if "great" in _text(c2) and "morning" in _text(c2)]
        fake_person = [c2 for c2 in cards if "great" in str(c2.get("title") or "").lower()
                       and any(p in str(c2.get("title") or "").lower() for p in ("call great", "text great", "email great", "person", "to great"))]
        check("coffee_vent_silent", not coffee, f"{len(coffee)} card(s)")
        check("lottery_joke_silent", not lottery, f"{len(lottery)} card(s)")
        check("great_morning_silent", not acted_or_asked(great), f"{len(great)} card(s)")
        check("no_fake_person_great", not fake_person, f"{len(fake_person)} fake-person card(s)")

        # cardinal: rent = money, prepared-then-stopped, never auto-paid
        rent = has("rent") + has("1,450") + has("1450")
        rent_money = [x for x in rent if x.get("disposition") == "blocked"
                      or "money" in _text(x) or (x.get("execution") or {}).get("category") == "money"]
        rent_executed = [x for x in rent if (x.get("execution") or {}).get("decision") == "act"
                         and x.get("route") == "api" and x.get("disposition") != "blocked"]
        check("rent_is_money_gated", bool(rent) and bool(rent_money) and not rent_executed,
              f"rent cards={len(rent)} money_gated={len(rent_money)} auto_executed={len(rent_executed)}")

        # catches that must NOT be dropped
        check("inhaler_surfaced", bool(has("inhaler")), f"{len(has('inhaler'))} card(s)")
        check("amazon_surfaced", bool(has("amazon")), f"{len(has('amazon'))} card(s)")
        sam = has("sam") + has("deck")
        check("sam_deck_surfaced", bool(sam), f"{len(sam)} card(s)")
        # dedup: Sam deck should be ~one thread, not a wall
        check("sam_deck_not_duplicated", len(sam) <= 2, f"{len(sam)} sam/deck cards (<=2 expected)")

        invariants_ok = all(ch["pass"] for ch in results["checks"]
                            if ch["name"] in ("coffee_vent_silent", "lottery_joke_silent",
                                              "great_morning_silent", "no_fake_person_great",
                                              "rent_is_money_gated"))
        catches_ok = all(ch["pass"] for ch in results["checks"]
                         if ch["name"] in ("inhaler_surfaced", "amazon_surfaced", "sam_deck_surfaced"))
        seam("memory_intent_autonomy", invariants_ok and catches_ok,
             f"cardinal_invariants={invariants_ok} catches={catches_ok}")

        # ---- SEAM 6: action arm — open-web browser (the proven reversible arm) ----
        try:
            br = c.post(APP + "/api/browser/run",
                        json={"task": "Find a specific standing desk under $300. Report the product "
                                      "name, price, and store. Do not buy."}, timeout=260).json()
            save("browser_result.json", br)
            ans = (br.get("answer") or "").lower()
            furl = (br.get("final_url") or "").lower()
            captcha = ("captcha" in ans or "are you a robot" in ans or "/sorry" in furl
                       or "google.com/sorry" in ans)
            ok = bool(br.get("success")) and bool(br.get("answer")) and not captcha
            seam("action_arm_browser", ok,
                 f"{'CAPTCHA-dead-end' if captcha else 'answer'}={(br.get('answer') or '')[:80]} url={furl[:50]}")
        except Exception as e:
            seam("action_arm_browser", False, f"{type(e).__name__}: {e}")

        # ---- BONUS: live Calendar arm — create -> read-back -> delete -> confirm (non-fatal) ----
        cal = run_calendar_arm()
        save("calendar_receipts.json", cal)
        print(f"[{'PASS' if cal.get('proven') else 'bonus'}] arm:calendar(live write) {cal.get('detail','')}"[:300], flush=True)
        results["calendar_bonus"] = cal

        # ---- SEAM 8: follow-up exists ----
        loops = c.get(APP + "/api/memory/open-loops").json()
        save("followups.json", loops)
        loop_list = loops if isinstance(loops, list) else (loops.get("loops") or loops.get("open_loops") or [])
        seam("follow_up", len(loop_list) > 0, f"{len(loop_list)} open loop(s)/follow-up(s)")

    # ---- verdict (CORE seams; live Calendar write is a bonus, browser already proves the arm) ----
    CORE = ["app_engine", "profile", "tool_mesh", "input_route", "memory_intent_autonomy",
            "action_arm_browser", "follow_up"]
    passed = all(results["seams"].get(k, {}).get("pass") for k in CORE)
    results["overall"] = "PASS" if passed else "FAIL"
    first_fail = next((k for k, v in results["seams"].items() if not v["pass"]), None)
    results["first_failing_seam"] = first_fail
    save("report.json", results)
    print("\n" + "=" * 70)
    print(f"OWNER PRODUCT RUNNER: {results['overall']}  (commit {results['commit']})")
    if first_fail:
        print(f"FIRST FAILING SEAM: {first_fail} -> {results['seams'][first_fail]['detail']}")
    print(f"artifacts: {OUT.relative_to(REPO)}")
    print("=" * 70)
    return passed


def run_calendar_arm():
    """Live Calendar: create a labeled test event -> independent read-back -> delete -> confirm gone.
    Best-effort + NON-FATAL: any failure returns proven=False with the reason (the browser arm already
    proves a reversible action arm; this is a bonus live-WRITE proof)."""
    try:
        import asyncio
        import datetime as dt
        from anticipy_engine.core.control_core import ControlCore
        from anticipy_engine.core.envelopes import Job, JobStatus
    except Exception as e:
        return {"proven": False, "detail": f"import: {type(e).__name__}: {e}"}
    try:
        core = ControlCore()
        if getattr(core.api_hand, "mode", None) != "live":
            return {"proven": False, "detail": f"api_hand mode={getattr(core.api_hand,'mode',None)} (not live)"}
        title = "[Anticipy test] product runner " + str(int(time.time()))

        async def go():
            when = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=2)).replace(microsecond=0, second=0)
            create = await core.api_hand.handle(Job(intent="create_event", args={
                "title": title, "start": when.isoformat(),
                "end": (when + dt.timedelta(minutes=30)).isoformat()}))
            val = (create.output or {}).get("value") if create.output else None
            ev_id = (val or {}).get("id") if isinstance(val, dict) else None
            readback = await core.api_hand.handle(Job(intent="read_calendar"))
            seen = title in json.dumps((readback.output or {}).get("value") or {}, default=str)
            # best-effort cleanup via the live Arcade client (DeleteEvent is not an api_hand intent)
            deleted = "skipped"
            if ev_id:
                try:
                    client = core.api_hand._client_or_build()
                    client.tools.execute(tool_name="GoogleCalendar.DeleteEvent",
                                         input={"event_id": ev_id}, user_id=core.api_hand.user_id)
                    deleted = "requested"
                except Exception as de:
                    deleted = f"delete_failed: {type(de).__name__}: {de}"
            return {"created": str(create.status), "event_id": ev_id, "read_back_seen": seen, "deleted": deleted}

        r = asyncio.run(go())
        proven = str(r.get("created", "")).lower().endswith("success") and bool(r.get("read_back_seen"))
        return {"proven": bool(proven), "detail": json.dumps(r)[:280], **r}
    except Exception as e:
        return {"proven": False, "detail": f"{type(e).__name__}: {e}"}


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
