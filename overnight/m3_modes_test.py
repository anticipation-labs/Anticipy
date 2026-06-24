#!/usr/bin/env python3
"""M3 unit gate — the autonomy DIAL + trust ledger logic. The two invariants must hold in EVERY mode,
and trust must promote/demote. Run: engine/.venv/bin/python overnight/m3_modes_test.py"""
import sys, tempfile, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine"))
from anticipy_engine.proactive import autonomy_mode as am

fails = []
def check(name, cond, detail=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {('' if cond else ':: '+detail)}")
    if not cond: fails.append(name)

money = {"disposition": "blocked", "action": "prepare_purchase_path_without_payment"}
send  = {"disposition": "ask", "action": "draft_or_confirm_message"}
coffee_ask = {"disposition": "ask", "action": "execute_owner_task"}
coffee_do  = {"disposition": "do", "action": "execute_owner_task"}
lookup_ask = {"disposition": "ask", "action": "research_or_find_item", "route": "browser"}
reminder_do = {"disposition": "do", "action": "create_calendar_or_reminder"}

# INVARIANT 1: $4,200 spend stays CONFIRM (blocked) in EVERY mode — including Full-Send.
for mode in am.MODES:
    r = am.adjust(money, mode, trust_tier=2, confidence=1.0)
    check(f"money stays blocked in {mode}", r["disposition"] == "blocked", r["disposition"])
# send-to-a-human stays ask in Full-Send even at max trust
check("send stays ask in full_send",
      am.adjust(send, "full_send", trust_tier=2)["disposition"] == "ask")

# Full-Send DOES more: a reversible lookup ask becomes do
check("full_send upgrades reversible lookup ask->do",
      am.adjust(lookup_ask, "full_send")["disposition"] == "do")
# Limited ASKS more: a non-whitelist do becomes ask
check("limited downgrades reversible do->ask",
      am.adjust(coffee_do, "limited")["disposition"] == "ask")
# Limited still auto-does the tiny reversible whitelist (a reminder)
check("limited still auto-does a reminder",
      am.adjust(reminder_do, "limited")["disposition"] == "do")
# INVARIANT 2: below confidence floor, a do drops to ask in every mode
check("low-confidence do->ask (full_send)",
      am.adjust(coffee_do, "full_send", confidence=0.3)["disposition"] == "ask")

# TRUST LEDGER: 5 clean reps promote a task-type to tier 2; then Regular promotes its ask->do; a rejection demotes.
with tempfile.TemporaryDirectory() as d:
    led = am.TrustLedger(os.path.join(d, "trust.json"))
    tt = am.task_type(lookup_ask)   # an EXECUTABLE reversible web task (the executor can run it)
    for _ in range(5): led.record_clean(tt)
    check("5 clean reps -> tier 2", led.tier(tt) == 2, f"tier={led.tier(tt)}")
    check("regular promotes a trusted EXECUTABLE reversible ask->do",
          am.adjust(lookup_ask, "regular", trust_tier=led.tier(tt))["disposition"] == "do")
    led.record_rejection(tt)
    check("rejection demotes below tier 2", led.tier(tt) < 2, f"tier={led.tier(tt)}")
    # the dial NEVER promises an upgrade the executor can't run: an api task stays a confirm-first ask
    check("api task (execute_owner_task) NOT promoted even at max trust",
          am.adjust(coffee_ask, "full_send", trust_tier=2)["disposition"] == "ask")
    # even a trusted task-type can't promote a SEND or MONEY
    led2 = am.TrustLedger(os.path.join(d, "t2.json"))
    for _ in range(9): led2.record_clean(am.task_type(send))
    check("max-trust never promotes a send",
          am.adjust(send, "regular", trust_tier=led2.tier(am.task_type(send)))["disposition"] == "ask")

print(f"\nM3 MODES: {'ALL PASS' if not fails else f'{len(fails)} FAILED: '+', '.join(fails)}")
sys.exit(1 if fails else 0)
