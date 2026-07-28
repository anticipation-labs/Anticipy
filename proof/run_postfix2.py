"""Post-fix verification 2 (commit 2f7bd6b): reproduce the exact 4 failure
shapes from the conversational round and confirm each is fixed. Minimal LLM.
Plain Anticipy (no agent_goal delivery override) — released jobs fail fast at
the extension ("unknown goal"), so no browser LLM steps are burned.
"""
import json
import sys
import time

sys.path.insert(0, "/home/ubuntu/anticipy_app")

import requests

from brain.anticipy_core import Anticipy
from brain.conversation import Conversation, MockTransport
from brain.llm import LLM
from brain.memory import Memory

BASE = "http://127.0.0.1:8090"
OWNER = "omar-owner-001"
PHONE = "+16045550111"


def load_env():
    import os
    for raw in open("/home/ubuntu/anticipy_app/.env"):
        raw = raw.strip()
        if raw and not raw.startswith("#") and "=" in raw:
            k, v = raw.split("=", 1)
            os.environ.setdefault(k, v)


def get_job(jid):
    return requests.get(f"{BASE}/api/collections/jobs/records/{jid}", timeout=10).json()


def banner(t):
    print(f"\n{'='*70}\n{t}\n{'='*70}", flush=True)


def main():
    load_env()
    llm = LLM()
    assert llm.live
    a = Anticipy(memory=Memory(llm=llm), llm=llm, backend_url=BASE,
                 owner_id=OWNER, owner_phone=PHONE)
    transport = MockTransport()
    conv = Conversation(a, transport=transport, llm=llm)
    a.conversation = conv
    verdicts = {}

    def reply(text):
        print(f'\nOMAR: "{text}"', flush=True)
        r = conv.on_reply(PHONE, text)
        print(f"  classified: intent={r['intent']} pending={r['pending_id']} "
              f"changes={json.dumps(r['changes'])} acted={r['acted']}", flush=True)
        print(f"  ANTICIPY: {r['reply']!r}", flush=True)
        return r

    # ---------------- A. policy-hold reach-out
    banner("A. policy-held job must trigger a reach-out text")
    n_texts0 = len(transport.sent)
    out = a.hear("I'll send Sarah the pitch deck feedback tonight.")
    d = out["decision"]
    print(f"triage: {d.to_json()}", flush=True)
    jid_deck = a.loops[-1].job_id
    j = get_job(jid_deck)
    print(f"job {jid_deck}: status={j['status']}", flush=True)
    new_texts = transport.sent[n_texts0:]
    for t in new_texts:
        print(f"REACH-OUT (mock): {t['body']!r}", flush=True)
    verdicts["A"] = {
        "triage_needs_confirmation": d.needs_confirmation,
        "job_status": j["status"],
        "reach_out_sent": len(new_texts) > 0,
        "reach_out_text": new_texts[0]["body"] if new_texts else None,
        "pass": j["status"] == "awaiting_confirm" and len(new_texts) > 0,
    }
    print(f"A verdict: {verdicts['A']['pass']}", flush=True)

    # ---------------- B. ambiguous confirm with 2 pending + 1 needs_user
    banner("B. two pending + one needs_user: 'ok go for it' must clarify")
    out2 = a.hear("Sign me up for the SFU alumni newsletter with my email.")
    jid_news = a.loops[-1].job_id
    print(f"second held job {jid_news}: {get_job(jid_news)['status']}", flush=True)
    # a stuck needs_user job (the state the extension now writes at walls)
    r = requests.post(f"{BASE}/api/collections/jobs/records", json={
        "goal": "agent_goal",
        "params": json.dumps({"task": "check my Wells Fargo balance",
                              "start_url": "https://www.wellsfargo.com"}),
        "status": "needs_user", "owner": OWNER,
        "result": "refused: wellsfargo.com is a protected financial site",
        "device_id": "postfix2"}, timeout=10)
    jid_stuck = r.json()["id"]
    print(f"stuck needs_user job {jid_stuck} created", flush=True)
    pend = conv._pending()
    print(f"_pending() sees: {[(p['id'], p['status']) for p in pend]}", flush=True)
    stuck_excluded = all(p["id"] != jid_stuck for p in pend)

    rb = reply("ok go for it")
    j_deck = get_job(jid_deck)
    j_news = get_job(jid_news)
    j_stuck = get_job(jid_stuck)
    print(f"after ambiguous confirm: deck={j_deck['status']} news={j_news['status']} "
          f"stuck={j_stuck['status']}", flush=True)
    b1_pass = (rb["acted"] is None and j_deck["status"] == "awaiting_confirm"
               and j_news["status"] == "awaiting_confirm"
               and j_stuck["status"] == "needs_user" and stuck_excluded)
    print(f"B1 (clarify, no flip, stuck excluded): {b1_pass}", flush=True)

    rb2 = reply("the newsletter one — go ahead")
    j_deck = get_job(jid_deck)
    j_news = get_job(jid_news)
    b2_pass = (rb2["acted"] == f"released:{jid_news}"
               and j_news["status"] in ("queued", "running", "failed")
               and j_deck["status"] == "awaiting_confirm")
    print(f"after topical confirm: deck={j_deck['status']} news={j_news['status']} "
          f"acted={rb2['acted']}", flush=True)
    print(f"B2 (right job released): {b2_pass}", flush=True)
    verdicts["B"] = {"stuck_excluded": stuck_excluded, "clarify": rb["reply"],
                     "b1": b1_pass, "b2": b2_pass, "pass": b1_pass and b2_pass}

    # ---------------- C. decline with no matching job
    banner("C. 'forget it' about a topic with NO job must not cancel others")
    time.sleep(3)  # let the released newsletter job settle (fails fast: unknown goal)
    pend = conv._pending()
    print(f"_pending() before C: {[(p['id'], p['goal']) for p in pend]}", flush=True)
    rc = reply("actually forget the omakase dinner, we'll just cook at home")
    j_deck = get_job(jid_deck)
    c_pass = (j_deck["status"] == "awaiting_confirm"
              and not (rc["acted"] or "").startswith("cancelled"))
    print(f"after decline: deck={j_deck['status']} acted={rc['acted']}", flush=True)
    print(f"C verdict: {c_pass}", flush=True)
    verdicts["C"] = {"acted": rc["acted"], "deck_status": j_deck["status"],
                     "reply": rc["reply"], "pass": c_pass}

    # ---------------- D. no fabricated completions
    banner("D. decline deck, then ask + briefing: no claimed completions")
    rd0 = reply("and drop the Sarah pitch deck thing too, I'll do it myself")
    j_deck = get_job(jid_deck)
    print(f"deck after decline: {j_deck['status']}", flush=True)
    rd1 = reply("so did everything go out?")
    closed = a.review_loops()
    print(f"review_loops: {json.dumps(closed)}", flush=True)
    b = a.briefing()
    print(f"BRIEFING: {b}", flush=True)
    fabrication_markers = ["i sent", "i've sent", "sent it", "i booked",
                           "i've booked", "signed you up", "i subscribed",
                           "went out", "it's done", "already sent"]
    blob = (rd1["reply"] + " " + b).lower()
    fabricated = [m for m in fabrication_markers if m in blob]
    verdicts["D"] = {"deck_status": j_deck["status"], "ask_reply": rd1["reply"],
                     "briefing": b, "fabrication_markers_hit": fabricated,
                     "loops": closed,
                     "pass": j_deck["status"] == "cancelled" and not fabricated}
    print(f"D verdict (auto-check): {verdicts['D']['pass']} "
          f"(markers hit: {fabricated}) — final call needs human read of texts",
          flush=True)

    banner("FULL MOCK THREAD")
    for t in conv.threads.get(PHONE, []):
        who = "ANTICIPY" if t.role == "anticipy" else "   OMAR"
        print(f"  {who}: {t.text}", flush=True)

    with open("/home/ubuntu/anticipy_postfix2_results.json", "w") as f:
        json.dump(verdicts, f, indent=2, default=str)
    banner("DONE -> /home/ubuntu/anticipy_postfix2_results.json")


if __name__ == "__main__":
    main()
