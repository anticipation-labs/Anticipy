"""Helpers for the 20-scenario production proof. Hosted Railway worker is the
ONLY transcript processor; this module only feeds events, reads back state,
and drives a LOCAL Conversation object for texted replies (queue flips only)."""
import json, os, sys, time
import requests

PB = "https://backend-production-61e0a.up.railway.app"
LOG = "/tmp/prod20.log"

def log(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    with open(LOG, "a") as f:
        f.write(s + "\n")

def _get(path, **params):
    r = requests.get(f"{PB}{path}", params=params, timeout=15)
    r.raise_for_status()
    return r.json()

def feed(device, text, wait=45):
    """POST a transcript event, wait for the hosted worker to process it,
    return (event, new anticipy events since)."""
    before = time.time()
    r = requests.post(f"{PB}/api/collections/events/records",
                      json={"device_id": device, "kind": "transcript",
                            "text": text}, timeout=15)
    r.raise_for_status()
    ev = r.json()
    log(f"\n[{device}] TRANSCRIPT: {text!r}  (event {ev['id']})")
    deadline = time.time() + wait
    decision = ""
    while time.time() < deadline:
        cur = _get(f"/api/collections/events/records/{ev['id']}")
        decision = cur.get("decision", "")
        if decision:
            break
        time.sleep(2)
    log(f"  worker decision: {decision or 'TIMEOUT (unprocessed)'}")
    time.sleep(2)
    says = _get("/api/collections/events/records",
                filter=f'kind!="transcript" && created>="{ev["created"]}"',
                sort="created", perPage=20)["items"]
    for s in says:
        log(f"  {s['kind']}: {s['text']!r} (goal={s.get('goal','')})")
    return cur, says

def jobs(n=6, filt=""):
    items = _get("/api/collections/jobs/records", perPage=n, sort="-created",
                 **({"filter": filt} if filt else {}))["items"]
    for j in items:
        log(f"  job {j['id']}: {j['status']:16s} goal={j['goal']!r}")
    return items

def job(jid):
    return _get(f"/api/collections/jobs/records/{jid}")

def watch(jid, timeout=300):
    """Wait for a job to reach a terminal-ish status. No steering."""
    t0 = time.time()
    last = ""
    while time.time() - t0 < timeout:
        j = job(jid)
        if j["status"] != last:
            last = j["status"]
            log(f"  [{int(time.time()-t0):3d}s] job {jid} -> {last}")
        if last in ("done", "failed", "needs_user", "cancelled",
                    "awaiting_confirm"):
            return j
        time.sleep(5)
    j = job(jid)
    log(f"  TIMEOUT {timeout}s: job {jid} status={j['status']} — marking failed (honest)")
    requests.patch(f"{PB}/api/collections/jobs/records/{jid}",
                   json={"status": "failed", "result": "harness: wedged >cap, killed"},
                   timeout=15)
    return job(jid)

def result(jid):
    j = job(jid)
    log(f"  job {jid} FINAL: status={j['status']} result={j.get('result','')!r}")
    return j

# ---- local Conversation (queue flips + reply classification only) ----
sys.path.insert(0, "/home/ubuntu/anticipy_app")
from brain.llm import LLM
from brain.memory import Memory
from brain.anticipy_core import Anticipy
from brain.conversation import Conversation, MockTransport

_llm = LLM()
assert _llm.live, "need live LLM for reply classification"
antic = Anticipy(memory=Memory(llm=None), llm=_llm, backend_url=PB,
                 owner_phone="owner")
conv = Conversation(antic, transport=MockTransport(), llm=_llm)
antic.conversation = conv

def reply(phone, text):
    log(f"\n[{phone}] OWNER TEXTS: {text!r}")
    out = conv.on_reply(phone, text)
    log(f"  classified: intent={out['intent']} pending={out['pending_id']} "
        f"changes={out['changes']} acted={out['acted']}")
    log(f"  ANTICIPY REPLIES: {out['reply']!r}")
    return out

log(f"prod20 helpers loaded · PB={PB} · llm={_llm.model}")
