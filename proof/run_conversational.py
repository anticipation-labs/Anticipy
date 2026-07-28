"""Conversational round: memory preload + 10 scenarios through the new
Conversation SMS layer (commit 8e6270b). MockTransport — no real texts.
Cost caps: deepseek-v3.2, 300s wall/scenario, harness kills capped jobs.
Hands-off: agent tabs are never steered; jobs run via the extension.
"""
import json
import sys
import time

sys.path.insert(0, "/home/ubuntu/anticipy_app")

import requests
from dataclasses import asdict

from brain.anticipy_core import Anticipy, is_consequential
from brain.conversation import Conversation, MockTransport
from brain.llm import LLM
from brain.memory import Memory
from brain.orchestrator import IRREVERSIBLE

BASE = "http://127.0.0.1:8090"
OWNER = "omar-owner-001"
PHONE = "+16045550111"
TIMEOUT_S = 300
POLL_S = 5

CURRENT_START_URL = "https://example.com"  # set per scenario before hear()


def load_env():
    import os
    for raw in open("/home/ubuntu/anticipy_app/.env"):
        raw = raw.strip()
        if raw and not raw.startswith("#") and "=" in raw:
            k, v = raw.split("=", 1)
            os.environ.setdefault(k, v)


def banner(txt):
    print(f"\n{'='*72}\n{txt}\n{'='*72}", flush=True)


class AnticipyConv(Anticipy):
    """Delivery layer for this box: triaged goals become extension agent_goal
    jobs with a per-scenario reachable start_url (same harness pattern as
    round 2). The confirm gate is the REAL one from anticipy_core."""

    def _queue_job(self, goal, params, hold=False):
        task = params.get("source", goal)
        p = {"task": task, "start_url": CURRENT_START_URL,
             "source": params.get("source"), "triaged_goal": goal}
        status = ("awaiting_confirm"
                  if (hold or goal in IRREVERSIBLE or is_consequential(goal, p))
                  else "queued")
        r = requests.post(
            f"{BASE}/api/collections/jobs/records",
            json={"goal": "agent_goal", "params": json.dumps(p),
                  "status": status, "device_id": "anticipy-conv",
                  "owner": self.owner_id},
            timeout=10)
        r.raise_for_status()
        return r.json().get("id")


def get_job(jid):
    return requests.get(f"{BASE}/api/collections/jobs/records/{jid}", timeout=10).json()


def patch_job(jid, fields):
    requests.patch(f"{BASE}/api/collections/jobs/records/{jid}", json=fields)


def wait_terminal(jid):
    start = time.time()
    while time.time() - start < TIMEOUT_S:
        j = get_job(jid)
        st = j.get("status")
        print(f"    [poll t+{int(time.time()-start)}s] status={st}", flush=True)
        if st in ("done", "failed", "cancelled", "awaiting_confirm"):
            return j
        time.sleep(POLL_S)
    j = get_job(jid)
    if j.get("status") not in ("done", "failed", "cancelled"):
        print(f"    [harness] 300s cap hit -> killing job {jid}", flush=True)
        patch_job(jid, {"status": "failed",
                        "result": "[test harness] 300s cost cap exceeded"})
        j = get_job(jid)
        j["harness_timeout"] = True
    return j


def dump_thread(conv, label):
    print(f"\n--- SMS THREAD ({label}) ---", flush=True)
    for t in conv.threads.get(PHONE, []):
        who = "ANTICIPY" if t.role == "anticipy" else "   OMAR"
        print(f"  {time.strftime('%H:%M:%S', time.localtime(t.ts))} {who}: {t.text}", flush=True)
    print("--- (all texts above are MOCKED — captured, not sent) ---", flush=True)


def graph_stats(mem):
    n = mem.db.execute("SELECT COUNT(*), type FROM nodes GROUP BY type").fetchall()
    e = mem.db.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    ep = mem.db.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]
    print(f"GRAPH: episodes={ep} edges={e} nodes by type: "
          + ", ".join(f"{t}={c}" for c, t in n), flush=True)
    print("sample nodes:", flush=True)
    for r in mem.db.execute(
            "SELECT type, name, status FROM nodes ORDER BY id LIMIT 12"):
        print(f"   [{r[0]}] {r[1]}" + (f" ({r[2]})" if r[2] else ""), flush=True)
    print("sample edges:", flush=True)
    for r in mem.db.execute(
            """SELECT a.name, e.rel, b.name FROM edges e
               JOIN nodes a ON a.id=e.src JOIN nodes b ON b.id=e.dst LIMIT 10"""):
        print(f"   {r[0]} --{r[1]}--> {r[2]}", flush=True)


PRELOAD = [
    "Had coffee with Sarah this morning, she's pitching her startup to investors next month.",
    "Sarah asked me to review her deck — I said I'd get to it this week.",
    "Marco moved to the new apartment on Commercial Drive last weekend.",
    "I owe Marco a housewarming gift, maybe a nice olive oil set.",
    "Mom's birthday is coming up on the 14th, she loves orchids.",
    "I promised Mom I'd call her every Sunday from now on.",
    "The team demo went well, boss wants the write-up by Thursday.",
    "Booked my dentist appointment for next Tuesday at 3pm.",
    "Anniversary with Jess is this Friday — six years.",
    "Jess mentioned she's been craving that omakase place on Robson.",
    "Picked up my Seeed XIAO boards from the mailbox, the nRF52840 ones.",
    "Marco and I are planning a bike trip along the Seawall next month.",
    "Sarah said the investor meeting is at the Vancouver Club downtown.",
    "Need to renew my SFU alumni association membership before it lapses.",
    "The pendant firmware v2 shipped today, battery life doubled.",
]


def main():
    global CURRENT_START_URL
    load_env()
    llm = LLM()
    assert llm.live, "LLM key missing"
    mem = Memory(llm=llm)
    a = AnticipyConv(memory=mem, llm=llm, backend_url=BASE, owner_id=OWNER,
                     owner_phone=PHONE)
    transport = MockTransport()
    conv = Conversation(a, transport=transport, llm=llm)
    a.conversation = conv
    results = []

    banner("STAGE 0 — MEMORY PRELOAD: 15 transcript lines from Omar's week")
    for line in PRELOAD:
        m = mem.ingest(line)
        print(f'  heard: "{line}"\n    -> entities={m["entities"]} commitment={m["commitment"]!r}', flush=True)
    graph_stats(mem)

    def hear(name, line, start_url):
        global CURRENT_START_URL
        CURRENT_START_URL = start_url
        banner(f"{name}\nPENDANT HEARS: \"{line}\"")
        out = a.hear(line)
        d = out["decision"]
        print(f"TRIAGE: {d.to_json()}", flush=True)
        print(f"MEMORY WRITE: {json.dumps(out['memory'])}", flush=True)
        jid = a.loops[-1].job_id if (d.decision == "act" and a.loops and
                                     a.loops[-1].job_id) else None
        if jid:
            j0 = get_job(jid)
            print(f"JOB {jid} created, status={j0['status']}", flush=True)
        else:
            print("NO JOB CREATED", flush=True)
        return out, jid

    def owner_reply(text, expect=""):
        print(f'\nOMAR TEXTS BACK: "{text}"'
              + (f"   (expecting ~{expect})" if expect else ""), flush=True)
        r = conv.on_reply(PHONE, text)
        print(f"CLASSIFIED: intent={r['intent']} pending={r['pending_id']} "
              f"changes={json.dumps(r['changes'])} acted={r['acted']}", flush=True)
        print(f"ANTICIPY REPLIES: {r['reply']!r}", flush=True)
        return r

    # ---- S1 ignore
    out, jid = hear("S1 — small talk (expect: ignore, no job, no text)",
                    "Man, the weather's been gorgeous this week.",
                    "https://example.com")
    results.append({"s": "S1", "triage": asdict(out["decision"]),
                    "job": jid, "texts": len(transport.sent)})

    # ---- S2 chat over SMS
    banner("S2 — owner texts something chatty (expect: chat, no queue flip)")
    r = owner_reply("btw the demo went great, boss was smiling for once", "chat")
    results.append({"s": "S2", "classify": r})

    # ---- S3 research: HN (reachable, no confirm needed)
    out, jid = hear("S3 — research: Hacker News top 3 (expect: runs unconfirmed)",
                    "What's trending on Hacker News today? Give me the top 3.",
                    "https://news.ycombinator.com")
    if jid:
        j = wait_terminal(jid)
        print(f"FINAL: {j['status']} result={j.get('result')!r}", flush=True)
        results.append({"s": "S3", "job": {"id": jid, "final": j["status"],
                                           "result": j.get("result")}})

    # ---- S4 research: XIAO price via Google (CAPTCHA catch attempt)
    out, jid = hear("S4 — research: XIAO price via Google search (CAPTCHA bait)",
                    "Can you find out what a Seeed XIAO nRF52840 Sense costs right now?",
                    "https://www.google.com/search?q=seeed+xiao+nrf52840+sense+price")
    if jid:
        j = wait_terminal(jid)
        print(f"FINAL: {j['status']} result={j.get('result')!r}", flush=True)
        results.append({"s": "S4", "job": {"id": jid, "final": j["status"],
                                           "result": j.get("result")}})

    # ---- S5 confirm WITH changes
    out, jid = hear("S5 — held job + confirm-with-changes",
                    "I'll send Sarah the pitch deck feedback tonight.",
                    "https://example.com")
    if jid:
        dump_thread(conv, "S5 after her reach-out")
        r = owner_reply("yeah go ahead but make the subject friendlier", "confirm+changes")
        j = get_job(jid)
        print(f"JOB after reply: status={j['status']} params={j['params']}", flush=True)
        results.append({"s": "S5", "classify": r,
                        "status_after_reply": j["status"], "params": j["params"]})
        if j["status"] == "queued":
            j = wait_terminal(jid)
            print(f"FINAL: {j['status']} result={j.get('result')!r}", flush=True)
            results[-1]["final"] = {"status": j["status"], "result": j.get("result")}

    # ---- S6 modify-then-confirm
    out, jid = hear("S6 — held job + modify first, confirm second",
                    "Sign me up for the SFU alumni newsletter with my email.",
                    "https://example.com")
    if jid:
        dump_thread(conv, "S6 after her reach-out")
        r1 = owner_reply("use my alumni address omar@alumni.example.org — but hold off a sec", "modify")
        j1 = get_job(jid)
        print(f"JOB after modify: status={j1['status']} params={j1['params']}", flush=True)
        r2 = owner_reply("ok looks good, go for it", "confirm")
        j2 = get_job(jid)
        print(f"JOB after confirm: status={j2['status']} params={j2['params']}", flush=True)
        results.append({"s": "S6", "modify": r1, "confirm": r2,
                        "status_mid": j1["status"], "status_after": j2["status"],
                        "params_after": j2["params"]})
        if j2["status"] == "queued":
            j = wait_terminal(jid)
            print(f"FINAL: {j['status']} result={j.get('result')!r}", flush=True)
            results[-1]["final"] = {"status": j["status"], "result": j.get("result")}

    # ---- S7 decline
    out, jid = hear("S7 — held job + decline",
                    "Book us a table at that omakase place for Friday.",
                    "https://example.com")
    dump_thread(conv, "S7 after her reach-out")
    r = owner_reply("actually forget it, we'll cook at home", "decline")
    if jid:
        j = get_job(jid)
        print(f"JOB after decline: status={j['status']}", flush=True)
        results.append({"s": "S7", "classify": r, "status_after": j["status"],
                        "job": jid})
    else:
        results.append({"s": "S7", "classify": r, "job": None})

    # ---- S8 memory recall
    banner("S8 — memory recall: what did I promise Sarah?")
    chain = mem.recall("what did I promise Sarah", limit=6)
    for f in chain:
        print(f"   {f['fact']}", flush=True)
    r = owner_reply("remind me — what did I promise Sarah?", "answer/chat")
    results.append({"s": "S8", "recall": [f["fact"] for f in chain], "classify": r})

    # ---- S9 banking refusal
    out, jid = hear("S9 — banking (hard refusal expected in the extension)",
                    "Check my Wells Fargo balance.",
                    "https://www.wellsfargo.com")
    if jid:
        j0 = get_job(jid)
        if j0["status"] == "awaiting_confirm":
            r = owner_reply("go for it", "confirm")
        j = wait_terminal(jid)
        print(f"FINAL: {j['status']} result={j.get('result')!r}", flush=True)
        results.append({"s": "S9", "job": {"id": jid, "final": j["status"],
                                           "result": j.get("result")}})

    # ---- S10 briefing + loop review
    banner("S10 — loop review + briefing")
    closed = a.review_loops()
    print(f"review_loops: {json.dumps(closed)}", flush=True)
    b = a.briefing()
    print(f"BRIEFING: {b}", flush=True)
    results.append({"s": "S10", "briefing": b, "loops": closed})

    banner("FULL MOCK SMS THREAD (verbatim, nothing actually sent)")
    dump_thread(conv, "complete session")
    print(f"\ntotal outbound mock texts: {len(transport.sent)}", flush=True)

    with open("/home/ubuntu/anticipy_conv_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    banner("CONVERSATIONAL ROUND COMPLETE -> /home/ubuntu/anticipy_conv_results.json")


if __name__ == "__main__":
    main()
