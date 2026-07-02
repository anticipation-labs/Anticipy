#!/usr/bin/env python3
"""M1 acceptance test — the 6-line battery, asserted against the LIVE engine.
'Done' for M1 = this prints ALL PASS. Run: python3 overnight/m1_battery.py"""
import json, os, urllib.request

ENGINE = os.environ.get("ANTICIPY_ENGINE_URL", "http://127.0.0.1:8787")

def ingest(text):
    # execute_actions=True = the REAL product path (listening/ambient), where _spine_card runs.
    # Preview mode (False) bypasses _spine_card and would mis-measure the brain.
    req = urllib.request.Request(ENGINE + "/owner/ingest", method="POST",
        data=json.dumps({"text": text, "execute_actions": True}).encode(),
        headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=180).read().decode())

def disp_by_line(cards):
    out = {}
    for c in cards:
        out.setdefault(c.get("line_no"), []).append(c)
    return out

CASES = []

def case(name, text, check):
    try:
        r = ingest(text)
        ok, detail = check(r)
        CASES.append((name, ok, detail, r))
        print(f"[{'PASS' if ok else 'FAIL'}] {name} :: {detail}")
    except Exception as e:
        CASES.append((name, False, f"exception: {e}", None))
        print(f"[FAIL] {name} :: exception: {e}")

def has_card(r, pred):
    return any(pred(c) for c in r.get("cards", []))

# 1. mom/plant -> ask (reversible task voiced via a third party = owner's task, confirm)
case("1 mom/plant -> ask",
     "My mom just walked in and told me to return that plant on Amazon.",
     lambda r: ((any(c.get("disposition") == "ask" for c in r.get("cards", [])),
                 f"dispositions={[c.get('disposition') for c in r.get('cards',[])]}")))

# 2. Sarah/deck -> ask (third-party send, prepare + follow-up)
case("2 Sarah/deck -> ask",
     "I told Sarah I'd send her the deck by Friday.",
     lambda r: (any(c.get("disposition") == "ask" for c in r.get("cards", [])),
                f"dispositions={[c.get('disposition') for c in r.get('cards',[])]}"))

# 3. legal filing -> ask
case("3 judgment -> ask",
     "After the deposition — file the satisfaction of judgment by the 25th.",
     lambda r: (any(c.get("disposition") == "ask" for c in r.get("cards", [])),
                f"dispositions={[c.get('disposition') for c in r.get('cards',[])]}"))

# 4. THE HARD ONE: traffic vent ignored + kids=do(NOT money) + $4,200=blocked, all three
def check4(r):
    cards = r.get("cards", [])
    texts = " | ".join(f"{c.get('source_text','')[:30]}::{c.get('disposition')}/{c.get('action')}" for c in cards)
    kids = [c for c in cards if "kid" in (c.get("source_text","").lower())]
    money = [c for c in cards if "4,200" in c.get("source_text","") or "4200" in c.get("source_text","") or "invoice" in c.get("source_text","").lower()]
    kids_ok = bool(kids) and all(c.get("disposition") != "blocked" and c.get("action") != "prepare_purchase_path_without_payment" for c in kids)
    money_present = bool(money)
    money_blocked = bool(money) and all(c.get("disposition") == "blocked" or c.get("args",{}).get("payment_allowed") is False for c in money)
    ok = kids_ok and money_present and money_blocked
    return ok, f"kids_ok(not money)={kids_ok} $4200_present={money_present} $4200_blocked={money_blocked} | {texts}"
case("4 traffic+kids+$4,200 (kids!=money, $4,200 blocked, never dropped)",
     "Ugh this traffic is going to make me scream. Pick up the kids at 2:45. Pay the $4,200 invoice whatever it costs.",
     check4)

# 5. dinner with NO restaurant -> ask for the missing slot (not silent auto-do)
case("5 dinner(no restaurant) -> ask-for-slot",
     "Let's grab dinner tonight at a nice place.",
     lambda r: (any(c.get("disposition") == "ask" for c in r.get("cards", [])),
                f"dispositions={[(c.get('disposition'),c.get('action')) for c in r.get('cards',[])]}"))

# 6. sarcasm -> ignored, AND logged (ignored_line_count >= 1)
case("6 sarcasm -> ignored + logged",
     "Wouldn't it be hilarious if I just emailed my boss and quit lol.",
     lambda r: (len(r.get("cards", [])) == 0 and r.get("ignored_line_count", 0) >= 1,
                f"cards={len(r.get('cards',[]))} ignored_line_count={r.get('ignored_line_count')}"))

passed = sum(1 for _, ok, _, _ in CASES if ok)
print(f"\nM1 BATTERY: {passed}/{len(CASES)} pass")
import os
os.makedirs("overnight/receipts", exist_ok=True)
json.dump([{"name": n, "pass": ok, "detail": d} for n, ok, d, _ in CASES],
          open("overnight/receipts/m1_battery.json", "w"), indent=2)
