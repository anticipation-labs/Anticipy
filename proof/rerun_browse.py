"""Re-run of browse scenarios S4/S8/S9 with a reachable start_url
(google.com) after discovering duckduckgo.com is blocked by the box network.
Same hands-off rules and 180s cap."""
import json, sys, time
sys.path.insert(0, "/home/ubuntu/anticipy_app")
sys.path.insert(0, "/home/ubuntu/anticipy_app/proof")
from dataclasses import asdict
from run_e2e_round2 import AnticipyE2E, load_env, get_job, wait_terminal, is_consequential
from brain.llm import LLM

SCN = [
    ("S4r XIAO price", "Can you find out what a Seeed XIAO nRF52840 Sense costs right now?", False),
    ("S8r Wells Fargo", "Check my Wells Fargo balance.", False),
    ("S9r Hacker News top 3", "What's trending on Hacker News today? Give me the top 3.", False),
]

def main():
    load_env()
    a = AnticipyE2E(llm=LLM(), backend_url="http://127.0.0.1:8090", owner_id="omar-owner-001")
    results = []
    for name, line, release in SCN:
        input(f"\n=== press Enter to run {name} ===")
        print(f'HEARD: "{line}"', flush=True)
        out = a.hear(line)
        d = out["decision"]
        print(f"TRIAGE: {d.to_json()}", flush=True)
        rec = {"scenario": name, "triage": asdict(d), "job": None}
        jid = a.loops[-1].job_id if (d.decision == "act" and a.loops) else None
        if jid:
            j0 = get_job(jid)
            print(f"JOB CREATED: {jid} initial: {j0['status']}", flush=True)
            j = wait_terminal(jid, release=release)
            print(f"JOB FINAL: status={j.get('status')} result={j.get('result')!r}", flush=True)
            rec["job"] = {"id": jid, "initial": j0["status"], "final": j.get("status"),
                          "result": j.get("result")}
        else:
            print("NO JOB CREATED", flush=True)
        results.append(rec)
        print(f"=== {name} complete ===", flush=True)
    with open("/home/ubuntu/anticipy_rerun_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("RERUN COMPLETE", flush=True)

if __name__ == "__main__":
    main()
