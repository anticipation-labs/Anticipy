"""End-to-end check of the settled-plan fix through the real hear() path
against the local PocketBase: the exact production line must now produce a
HELD card and one go-ahead text, not silence."""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for raw in open(os.path.join(os.path.dirname(__file__), "..", ".env")):
    raw = raw.strip()
    if raw and not raw.startswith("#") and "=" in raw:
        k, v = raw.split("=", 1)
        os.environ.setdefault(k, v.strip().strip('"'))

import requests                                # noqa: E402
from brain.llm import LLM                      # noqa: E402
from brain.memory import Memory                # noqa: E402
from brain.anticipy_core import Anticipy       # noqa: E402

PB = "http://127.0.0.1:8090"
LINE = ("Yeah I know we should really go out for dinner yeah we totally "
        "should house tomorrow at Earl's at 2:30 in West Van yeah for sure "
        "I'd be down for that")

llm = LLM()
a = Anticipy(memory=Memory(":memory:", llm=llm), llm=llm, backend_url=PB)
texts = []
a.notify_owner = lambda m, channel="sms": (texts.append(m), {"ok": 1})[1]

before = {j["id"] for j in requests.get(
    f"{PB}/api/collections/jobs/records",
    params={"perPage": 200}).json()["items"]}

out = a.hear(LINE)
d = out["decision"]
print("decision :", d.decision)
print("reason   :", repr(d.reason))
print("says     :", repr(out.get("anticipy_says")))
print("texts    :", texts)

items = requests.get(f"{PB}/api/collections/jobs/records",
                     params={"perPage": 200, "sort": "-created"}).json()["items"]
new = [j for j in items if j["id"] not in before]
for j in new:
    print("new job  :", j["status"], repr(j["goal"]))
    print("params   :", j["params"][:300])

ok = (d.decision == "act" and new
      and new[0]["status"] == "awaiting_confirm"
      and (texts or out.get("anticipy_says")))
print("\nRESULT:", "PASS" if ok else "FAIL")
