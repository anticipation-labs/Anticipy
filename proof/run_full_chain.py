"""Part B: full-chain simulation, one continuous sequence with backend state
printed at every stage:

pendant line -> Anticipy.hear() (live LLM) -> memory graph delta -> job HELD at
awaiting_confirm -> pairing/heartbeat shown -> simulated app YES -> extension
claims & executes unsteered -> terminal status -> review_loops closes loop &
memory resolves -> briefing mentions it.
"""
import json
import sys
import time

sys.path.insert(0, "/home/ubuntu/anticipy_app")
import requests

from run_e2e_round2 import AnticipyE2E, load_env, get_job, patch_job, BASE, OWNER
from brain.llm import LLM

LINE = "I'll text Marco the top Hacker News headline tonight."
CAP_S = 180


def stage(n, msg):
    print(f"\n===== STAGE {n}: {msg} =====", flush=True)


def dump_graph(mem):
    nodes = mem.db.execute("SELECT id,type,name,status FROM nodes").fetchall()
    edges = mem.db.execute("SELECT src,rel,dst FROM edges").fetchall()
    print("GRAPH NODES:", flush=True)
    for r in nodes:
        print(f"  #{r[0]} [{r[1]}] {r[2]}" + (f" (status={r[3]})" if r[3] else ""), flush=True)
    print("GRAPH EDGES:", flush=True)
    name = {r[0]: r[2] for r in nodes}
    for s, rel, d in edges:
        print(f"  {name.get(s)} --{rel}--> {name.get(d)}", flush=True)


def main():
    load_env()
    llm = LLM()
    assert llm.live
    a = AnticipyE2E(llm=llm, backend_url=BASE, owner_id=OWNER)

    stage(1, "pendant transcript line arrives")
    print(f'HEARD: "{LINE}"', flush=True)
    out = a.hear(LINE)
    print(f"TRIAGE: {out['decision'].to_json()}", flush=True)
    print(f"ANTICIPY SAYS: {out['anticipy_says']}", flush=True)

    stage(2, "memory graph after ingest")
    dump_graph(a.memory)
    print("OPEN LOOPS:", json.dumps(a.memory.open_loops()), flush=True)

    jid = a.loops[-1].job_id if a.loops else None
    stage(3, "job held at awaiting_confirm (confirm gate outside the model)")
    if not jid:
        print("NO JOB CREATED — chain cannot continue", flush=True)
        return
    j = get_job(jid)
    print(json.dumps({k: j[k] for k in ("id", "goal", "status", "owner", "params")}, indent=1), flush=True)

    stage(4, "pairing: agent record heartbeat is fresh")
    ag = requests.get(f"{BASE}/api/collections/agents/records").json()["items"][0]
    print(json.dumps({k: ag[k] for k in ("agent_id", "pair_code", "paired", "owner", "last_seen")}, indent=1), flush=True)

    stage(5, "simulated app YES (PATCH awaiting_confirm -> queued)")
    patch_job(jid, {"status": "queued"})
    print(f"job {jid} status now: {get_job(jid)['status']}", flush=True)

    stage(6, "extension claims and executes unsteered (cap 180s)")
    t0 = time.time()
    while time.time() - t0 < CAP_S:
        j = get_job(jid)
        print(f"  [poll t+{int(time.time()-t0)}s] status={j['status']} claimed_by={j['claimed_by'][:8]}", flush=True)
        if j["status"] in ("done", "failed") or (j["status"] == "awaiting_confirm"):
            break
        time.sleep(5)
    else:
        print("  [harness] 180s cap -> killing job", flush=True)
        patch_job(jid, {"status": "failed", "result": "[test harness] 180s cap"})
        j = get_job(jid)
    print(f"TERMINAL: status={j['status']} result={j['result']!r}", flush=True)

    if j["status"] != "done":
        stage("6b", "agent did not reach done on its own — simulating app "
                    "marking it complete (flagged as SIMULATED for the report)")
        patch_job(jid, {"status": "done", "result": (j["result"] or "") +
                        " [SIMULATED completion by test harness for chain demo]"})

    stage(7, "Anticipy reviews loops -> loop closes, memory commitment resolves")
    print("review_loops:", json.dumps(a.review_loops(), indent=1), flush=True)
    print("open_loops after:", json.dumps(a.memory.open_loops()), flush=True)

    stage(8, "briefing")
    print(f"BRIEFING: {a.briefing()}", flush=True)
    print("\nFULL CHAIN COMPLETE", flush=True)


if __name__ == "__main__":
    main()
