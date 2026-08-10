"""Real-Chrome battery for the site-defaults fixes: the unpacked extension
drives a LOCAL reservation-style page (nothing real is ever booked).

Three scenarios, exactly the live 2026-08-10 failure shapes:
  1. the widget opens with the site's own defaults (today, 6:30 PM) and the
     agreed slot EXISTS -> the agent must set the fields itself and finish,
     never stopping to ask about a default;
  2. the agreed time does NOT exist -> the agent must stop with needs_user
     naming what IS available, never inventing an option;
  3. the parked job from (2) resumes after the owner's text answer is folded
     into its authority (the exact patch _amend/_release apply) -> the agent
     must act on the answer and finish.
"""
import http.server
import json
import os
import sys
import threading
import time

import httpx
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8090"
EXT = "/home/ubuntu/anticipy_app/extension"
PORT = 8777

PAGE = """<!doctype html><html><head><title>Demo Bistro — Reservations</title>
</head><body><h1>Demo Bistro</h1><p>Make a reservation.</p>
<label>Party size <select id="p"><option>1 person</option>
<option selected>2 people</option><option>3 people</option>
<option>4 people</option></select></label>
<label>Date <select id="d"><option selected>Mon Aug 10</option>
<option>Tue Aug 11</option><option>Wed Aug 12</option></select></label>
<label>Time <select id="t">%OPTIONS%</select></label>
<button id="go" onclick="done()">Find a table</button>
<div id="out"></div>
<script>
function done(){
  document.getElementById('out').textContent =
    'Reservation confirmed for ' + document.getElementById('p').value +
    ' on ' + document.getElementById('d').value +
    ' at ' + document.getElementById('t').value + '. Confirmation #DEMO-42.';
}
</script></body></html>"""

WITH_NOON = PAGE.replace("%OPTIONS%", (
    "<option>11:30 AM</option><option>12:00 PM</option>"
    "<option>12:30 PM</option><option selected>6:30 PM</option>"
    "<option>7:00 PM</option>"))
NO_NOON = PAGE.replace("%OPTIONS%", (
    "<option selected>6:30 PM</option><option>7:00 PM</option>"
    "<option>7:30 PM</option>"))


class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = (WITH_NOON if self.path.startswith("/withnoon")
                else NO_NOON).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def clear_jobs():
    for it in httpx.get(f"{BASE}/api/collections/jobs/records",
                        params={"perPage": 200}).json()["items"]:
        httpx.delete(f"{BASE}/api/collections/jobs/records/{it['id']}")


def queue(goal, params):
    return httpx.post(f"{BASE}/api/collections/jobs/records", json={
        "goal": goal, "status": "queued", "params": json.dumps(params),
        "device_id": "anticipy-pendant-0001"}).json()


def watch(job_id, seconds=240):
    deadline = time.time() + seconds
    rec = {}
    while time.time() < deadline:
        time.sleep(3)
        rec = httpx.get(
            f"{BASE}/api/collections/jobs/records/{job_id}").json()
        if rec.get("status") in ("done", "failed", "needs_user",
                                 "awaiting_confirm", "cancelled"):
            break
    return rec


def main():
    key = os.environ.get("OPENROUTER_API_KEY")
    assert key, "need OPENROUTER_API_KEY in env"
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    clear_jobs()
    results = []
    scope = ('Task: Book lunch at the demo bistro for tomorrow at noon, '
             'party of 2. They said: "yes". Heard originally: lunch '
             'tomorrow around noon, the demo bistro')
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            "/tmp/anticipy_defaults_profile", headless=True,
            channel="chromium",
            args=[f"--disable-extensions-except={EXT}",
                  f"--load-extension={EXT}"])
        sw = None
        for _ in range(20):
            if ctx.service_workers:
                sw = ctx.service_workers[0]
                break
            time.sleep(1)
        assert sw, "extension service worker never started"
        sw.evaluate(
            """([base, key, model]) => chrome.storage.local.set({
                 backendUrl: base, openrouterKey: key, agentModel: model,
                 keyFetchedAt: Date.now(), owner: "batt" })""",
            [BASE, key, os.environ.get("ANTICIPY_MODEL",
                                       "google/gemini-2.5-flash")])
        time.sleep(2)

        # 1. defaults are fields to set: noon exists, agent must finish
        job = queue("Book lunch at the demo bistro for tomorrow at noon",
                    {"authorized": True, "approved_scope": scope,
                     "time": "noon", "party_size": "2",
                     "start_url": f"http://127.0.0.1:{PORT}/withnoon"})
        rec = watch(job["id"])
        res = (rec.get("result") or "")
        ok = (rec.get("status") == "done" and "12:00" in res
              and "Aug 11" in res)
        results.append(("sets date+time past site defaults", ok,
                        f"status={rec.get('status')} result={res[:110]!r}"))

        # 2. agreed time genuinely unavailable: honest stop, real options
        clear_jobs()
        job = queue("Book lunch at the demo bistro for tomorrow at noon",
                    {"authorized": True, "approved_scope": scope,
                     "time": "noon", "party_size": "2",
                     "start_url": f"http://127.0.0.1:{PORT}/nonoon"})
        rec = watch(job["id"])
        res = (rec.get("result") or "")
        ok = (rec.get("status") == "needs_user" and "6:30" in res
              and "confirmed" not in res.lower()
              and "booked" not in res.lower())
        results.append(("stops honestly when noon not offered", ok,
                        f"status={rec.get('status')} result={res[:110]!r}"))

        # 3. resume the parked run with the owner's answer (the exact patch
        # brain/conversation.py applies on his text)
        if rec.get("status") == "needs_user":
            params = json.loads(rec.get("params") or "{}")
            asked = rec.get("result") or ""
            params["approved_scope"] += (
                f' You stopped and asked: "{asked}". '
                f'They answered: "6:30 works, go" — that answer is final; '
                f'act on it.')
            params["needed"] = asked
            httpx.patch(f"{BASE}/api/collections/jobs/records/{rec['id']}",
                        json={"status": "queued",
                              "params": json.dumps(params)})
            rec2 = watch(rec["id"])
            res2 = (rec2.get("result") or "")
            ok = (rec2.get("status") == "done" and "6:30" in res2
                  and "Aug 11" in res2)
            results.append(("parked run resumes on the text answer", ok,
                            f"status={rec2.get('status')} "
                            f"result={res2[:110]!r}"))
        else:
            results.append(("parked run resumes on the text answer", False,
                            "no parked job to resume"))

        ctx.close()
    srv.shutdown()
    failed = [r for r in results if not r[1]]
    for name, ok, note in results:
        print(f"  {'ok  ' if ok else 'FAIL'} {name} — {note}")
    print(f"agent defaults chrome battery: "
          f"{len(results) - len(failed)}/{len(results)}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()


