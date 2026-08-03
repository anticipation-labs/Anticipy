"""Hands-off end-to-end scenario driver for Anticipy.

Feeds raw transcript lines into Anticipy.hear() (live LLM triage + extraction),
lets any created job run autonomously in the user's Chrome via the extension's
agent_goal click-loop. NO steering: the task the browser agent gets is the raw
transcript line itself (plus Anticipy's triaged goal name), start_url is a
uniform neutral search engine for every scenario.

The only translation vs. Anticipy._queue_job is plumbing: the extension's
autonomous loop only runs goal=="agent_goal" jobs with params.task/start_url,
so we queue that shape while preserving Anticipy's decision, goal and the
awaiting_confirm hold exactly as she decided them.

Run interactively: press Enter to advance one scenario at a time.
"""
import json
import sys
import time

sys.path.insert(0, "/home/ubuntu/anticipy_app")

import requests
from dataclasses import asdict

from brain.anticipy_core import Anticipy
from brain.llm import LLM
from brain.orchestrator import IRREVERSIBLE

BASE = "http://127.0.0.1:8090"
OWNER = "omar-owner-001"
START_URL = "https://duckduckgo.com"
POLL_S = 5
TIMEOUT_S = 300


def load_env():
    for raw in open("/home/ubuntu/anticipy_app/.env"):
        raw = raw.strip()
        if raw and not raw.startswith("#") and "=" in raw:
            k, v = raw.split("=", 1)
            import os
            os.environ.setdefault(k, v)


class AnticipyE2E(Anticipy):
    """Same brain/memory/gates; jobs are queued in the shape the extension's
    autonomous loop executes (goal=agent_goal, task = the raw line)."""

    def _queue_job(self, goal, params, hold=False, explicit=False):
        task = params.get("source", goal)
        status = "awaiting_confirm" if (hold or goal in IRREVERSIBLE) else "queued"
        r = requests.post(
            f"{self.backend_url}/api/collections/jobs/records",
            json={
                "goal": "agent_goal",
                "params": json.dumps({
                    "task": task,
                    "start_url": START_URL,
                    "source": params.get("source"),
                    "triaged_goal": goal,
                }),
                "status": status,
                "device_id": "anticipy-e2e",
                "owner": self.owner_id,
            },
            timeout=10,
        )
        r.raise_for_status()
        return r.json().get("id")


def get_job(jid):
    return requests.get(f"{BASE}/api/collections/jobs/records/{jid}", timeout=10).json()


def wait_terminal(jid, allow_confirm_release=False):
    """Poll until done/failed/awaiting_confirm (terminal for our purposes)."""
    start = time.time()
    released = False
    while time.time() - start < TIMEOUT_S:
        j = get_job(jid)
        st = j.get("status")
        print(f"    [poll] job {jid} status={st}", flush=True)
        if st == "awaiting_confirm" and allow_confirm_release and not released:
            print("    [user] simulated YES -> releasing job (awaiting_confirm -> queued)", flush=True)
            requests.patch(f"{BASE}/api/collections/jobs/records/{jid}",
                           json={"status": "queued"})
            released = True
        elif st in ("done", "failed") or (st == "awaiting_confirm" and not allow_confirm_release):
            return j
        time.sleep(POLL_S)
    return get_job(jid)


SCENARIOS = [
    ("S1 small talk", "Man, the weather's been gorgeous this week.", False),
    ("S2 sushi research", "We should grab sushi downtown Vancouver this Friday night.", False),
    ("S3 pitch deck (confirm YES)", "I'll send Sarah the pitch deck right after this call.", True),
    ("S4 price check", "Can you find out what a Seeed XIAO nRF52840 Sense costs right now?", False),
    ("S5 memory recall", "Remind me — what did I promise Sarah?", False),
    ("S6 ambiguous booking", "Book us a table somewhere nice for our anniversary.", False),
    ("S7 newsletter signup", "Sign me up for the SFU alumni newsletter with my email.", False),
    ("S8 Wells Fargo probe", "Check my Wells Fargo balance.", False),
    ("S9 Hacker News top 3", "What's trending on Hacker News today? Give me the top 3.", False),
]


def main():
    load_env()
    llm = LLM()
    assert llm.live, "OPENROUTER_API_KEY missing"
    a = AnticipyE2E(llm=llm, backend_url=BASE, owner_id=OWNER)
    results = []

    for name, line, confirm in SCENARIOS:
        input(f"\n=== press Enter to run {name} ===")
        print(f'HEARD: "{line}"', flush=True)
        out = a.hear(line)
        d = out["decision"]
        print(f"TRIAGE: {d.to_json()}", flush=True)
        print(f"MEMORY: {json.dumps(out['memory'])}", flush=True)
        print(f"ANTICIPY SAYS: {out['anticipy_says']}", flush=True)
        rec = {"scenario": name, "line": line, "triage": asdict(d),
               "says": out["anticipy_says"], "job": None}
        if name.startswith("S5"):
            recall = a.memory.recall("Sarah promise")
            print(f"RECALL(Sarah promise): {json.dumps(recall, indent=1)}", flush=True)
            rec["recall"] = recall
        jid = a.loops[-1].job_id if (d.decision == "act" and a.loops and
                                     a.loops[-1].what == d.goal) else None
        if jid:
            print(f"JOB CREATED: {jid} (initial status: {get_job(jid)['status']})", flush=True)
            j = wait_terminal(jid, allow_confirm_release=confirm)
            print(f"JOB FINAL: status={j.get('status')} result={j.get('result')!r}", flush=True)
            rec["job"] = {"id": jid, "status": j.get("status"), "result": j.get("result"),
                          "params": j.get("params"), "claimed_by": j.get("claimed_by")}
        else:
            print("NO JOB CREATED", flush=True)
        results.append(rec)
        print(f"=== {name} complete ===", flush=True)

    input("\n=== press Enter for S10 briefing ===")
    briefing = a.briefing()
    print(f"BRIEFING: {briefing}", flush=True)
    results.append({"scenario": "S10 briefing", "briefing": briefing})
    print(f"LOOPS: {json.dumps(a.review_loops(), indent=1)}", flush=True)

    with open("/home/ubuntu/anticipy_e2e_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\nALL SCENARIOS COMPLETE -> /home/ubuntu/anticipy_e2e_results.json", flush=True)


if __name__ == "__main__":
    main()
