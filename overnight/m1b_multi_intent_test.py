#!/usr/bin/env python3
"""M1b acceptance — bundled multi-intent lines must keep EVERY task (never drop one), while a single
intent with a subordinate clause must NOT over-split. Run after a fresh engine restart."""
import json, urllib.request

ENGINE = "http://127.0.0.1:8787"
def ingest(text):
    req = urllib.request.Request(ENGINE + "/owner/ingest", method="POST",
        data=json.dumps({"text": text, "execute_actions": True}).encode(),
        headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=180).read().decode())

fails = []
def check(name, cond, detail=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {'' if cond else ':: '+str(detail)}")
    if not cond: fails.append(name)

def srcs(r): return [(c.get("source_text") or "").lower() for c in r.get("cards", [])]
def has(r, *subs): return any(all(s in t for s in [sub.lower()]) for sub in subs for t in srcs(r))

# 1. the bug: "remind me to call the dentist AND email Priya" -> BOTH survive
r = ingest("Remind me to call the dentist tomorrow and email Priya the Q3 budget.")
s = srcs(r)
check("dentist+Priya -> both kept (>=2 cards)", len(r.get("cards", [])) >= 2, f"cards={len(r.get('cards',[]))} {s}")
check("  dentist survived", any("dentist" in t for t in s), s)
check("  Priya survived", any("priya" in t for t in s), s)

# 2. three distinct verbs -> three tasks
r = ingest("Book a haircut Saturday and cancel my gym membership and text Dad happy birthday.")
s = srcs(r)
check("haircut+gym+Dad -> 3 kept", len(r.get("cards", [])) >= 3, f"cards={len(r.get('cards',[]))} {s}")

# 3. M1a-consistent: kids (reversible) + $4,200 (money) in one 'and' line -> both, money blocked, kids not
r = ingest("Pick up the kids at 2:45 and pay the $4,200 invoice.")
cards = r.get("cards", [])
kids = [c for c in cards if "kid" in (c.get("source_text", "").lower())]
money = [c for c in cards if "4,200" in c.get("source_text", "") or "invoice" in c.get("source_text", "").lower()]
check("kids+$4,200 -> both kept", bool(kids) and bool(money), [(c.get('source_text'), c.get('disposition')) for c in cards])
check("  kids NOT money/blocked", bool(kids) and all(c.get("disposition") != "blocked" for c in kids))
check("  $4,200 blocked", bool(money) and all(c.get("disposition") == "blocked" for c in money))

# 4. CONSERVATIVE: a single call with a subordinate clause must NOT over-split into a bogus 2nd task
r = ingest("Remind me to call the dentist and tell them I'm running late.")
cards = r.get("cards", [])
check("single-call w/ subordinate clause not over-split (1 card, dentist kept)",
      len(cards) == 1 and any("dentist" in (c.get("source_text", "").lower()) for c in cards),
      [(c.get('source_text')) for c in cards])

print(f"\nM1b MULTI-INTENT: {'ALL PASS' if not fails else str(len(fails))+' FAILED: '+', '.join(fails)}")
import sys; sys.exit(1 if fails else 0)
