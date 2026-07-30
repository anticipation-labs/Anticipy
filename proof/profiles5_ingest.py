"""Five-profile full-day ingestion audit.

Multi-user is NOT in production (single-owner hosted worker), so each profile
gets its own LOCAL Anticipy brain with an isolated on-disk memory graph —
same code the hosted worker runs. Jobs queue into the local PocketBase so
ingestion doesn't spam production; the browser-task phase copies chosen tasks
to the production backend for the real extension to execute.

Usage: .venv/bin/python proof/profiles5_ingest.py [profile_id ...]
"""
import json, os, sys, time

sys.path.insert(0, "/home/ubuntu/anticipy_app")
for line in open("/home/ubuntu/anticipy_app/.env"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k, v.strip().strip('"'))

from brain.llm import LLM
from brain.memory import Memory
from brain.anticipy_core import Anticipy

PB_LOCAL = "http://127.0.0.1:8090"
OUT = "/home/ubuntu/profiles5_results.json"
LOG = "/home/ubuntu/profiles5_ingest.log"

def log(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    with open(LOG, "a") as f:
        f.write(s + "\n")

def run_profile(p, llm):
    mem_path = f"/home/ubuntu/profiles5_mem_{p['id']}.db"
    if os.path.exists(mem_path):
        os.remove(mem_path)
    mem = Memory(path=mem_path, llm=llm)
    antic = Anticipy(memory=mem, llm=llm, backend_url=PB_LOCAL,
                     owner_phone=p["id"])
    rec = {"id": p["id"], "who": p["who"], "lines": [], "recall": [],
           "jobs": []}
    log(f"\n{'='*70}\nPROFILE {p['id']} — {p['who']}\n{'='*70}")
    for item in p["day"]:
        out = antic.hear(item["text"])
        d = out.get("decision")
        dec = getattr(d, "decision", str(d))
        goal = getattr(d, "goal", None)
        says = out.get("anticipy_says", "")
        log(f"[{item['t']}] {item['text']!r}\n"
            f"    expect={item['expect']:20s} decision={dec} goal={goal}\n"
            f"    says={says!r}")
        rec["lines"].append({"t": item["t"], "text": item["text"],
                             "expect": item["expect"], "decision": dec,
                             "goal": goal, "says": says})
        time.sleep(1)
    for chk in p["recall_checks"]:
        ans = antic._answer_from_memory(chk["q"]) or "(no answer)"
        log(f"RECALL {chk['q']!r}\n    gold={chk['gold']!r}\n    got ={ans!r}")
        rec["recall"].append({"q": chk["q"], "gold": chk["gold"], "got": ans})
    for loop in antic.loops:
        rec["jobs"].append({"what": loop.what, "status": loop.status,
                            "job_id": loop.job_id})
        log(f"LOOP: {loop.what} status={loop.status} job={loop.job_id}")
    return rec

def main():
    data = json.load(open("/home/ubuntu/anticipy_app/proof/profiles5.json"))
    only = set(sys.argv[1:])
    llm = LLM()
    assert llm.live, "need live LLM"
    log(f"profiles5 ingest · llm={llm.model} · local PB={PB_LOCAL}")
    results = []
    if os.path.exists(OUT):
        results = json.load(open(OUT))
    done_ids = {r["id"] for r in results}
    for p in data["profiles"]:
        if only and p["id"] not in only:
            continue
        if p["id"] in done_ids and not only:
            log(f"skip {p['id']} (already done)")
            continue
        results = [r for r in results if r["id"] != p["id"]]
        results.append(run_profile(p, llm))
        json.dump(results, open(OUT, "w"), indent=1)
    log(f"\nDONE — results in {OUT}")

if __name__ == "__main__":
    main()
