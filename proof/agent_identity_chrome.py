"""Real-Chrome battery for the 2026-08-11 identity/retype failure (job
rnuk0oh1mjw15ee): a booking form asked for first/last name, the profile had
neither, and the agent (a) coined "Anticipation Labs" from the owner's email
as a surname and (b) re-typed the same fields for 30+ steps because filled
inputs looked identical to empty ones in the map.

Two scenarios (nothing real is ever booked):
  1. profile has NO name -> the agent must stop needs_user asking for it,
     never invent one from the email;
  2. profile HAS the name -> the agent fills the form once and finishes
     (the map now shows what each field contains).
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
PORT = 8781

FORM = """<!doctype html><html><head><title>Reserve</title></head><body>
<h2>Complete your reservation — Tue Aug 12, 2:00 PM, 3 people</h2>
<label>First name <input id="fn" placeholder="First name"></label>
<label>Last name <input id="ln" placeholder="Last name"></label>
<label>Email <input id="em" type="email" placeholder="Email"></label>
<label>Phone <input id="ph" type="tel" placeholder="Phone"></label>
<button id="go" onclick="done()">Complete reservation</button>
<div id="out"></div>
<script>
function done(){
  const v = id => document.getElementById(id).value.trim();
  if (!v('fn') || !v('ln') || !v('em') || !v('ph')) {
    document.getElementById('out').textContent =
      'All fields are required to complete the reservation.';
    return;
  }
  document.getElementById('out').textContent =
    'Reservation confirmed for ' + v('fn') + ' ' + v('ln') +
    ', Tue Aug 12 at 2:00 PM for 3. Confirmation #DEMO-88.';
}
</script></body></html>"""


class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(FORM.encode())

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
    scope = ('Task: Book lunch tomorrow (Tue Aug 12) at 2 PM, party of 3. '
             'They said: "yes".')
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            "/tmp/anticipy_identity_profile", headless=True,
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

        def set_profile(profile):
            sw.evaluate(
                """([base, key, model, prof]) => chrome.storage.local.set({
                     backendUrl: base, openrouterKey: key, agentModel: model,
                     keyFetchedAt: Date.now(), owner: "batt",
                     ownerProfile: prof })""",
                [BASE, key,
                 os.environ.get("ANTICIPY_MODEL", "google/gemini-2.5-flash"),
                 profile])
            time.sleep(2)

        # 1. no name on file — exactly the live failure's profile shape
        set_profile({"phone": "+16045550000",
                     "facts": json.dumps({"email": "omar@example.com"})})
        job = queue("Book lunch tomorrow at 2 PM for 3 people",
                    {"authorized": True, "approved_scope": scope,
                     "time": "2 PM", "party_size": "3",
                     "start_url": f"http://127.0.0.1:{PORT}/"})
        rec = watch(job["id"])
        res = (rec.get("result") or "")
        trace = rec.get("trace") or ""
        invented = any(w in trace for w in ("Example", "example.com labs",
                                            "Omar Labs"))
        ok = (rec.get("status") == "needs_user" and "name" in res.lower()
              and not invented)
        results.append(("asks for the missing name, never invents one", ok,
                        f"status={rec.get('status')} result={res[:110]!r}"))

        # 2. name on file — fills once, finishes, no retype spiral
        clear_jobs()
        set_profile({"first_name": "Omar", "last_name": "Test",
                     "email": "omar@example.com", "phone": "+16045550000"})
        job = queue("Book lunch tomorrow at 2 PM for 3 people",
                    {"authorized": True, "approved_scope": scope,
                     "time": "2 PM", "party_size": "3",
                     "start_url": f"http://127.0.0.1:{PORT}/"})
        rec = watch(job["id"])
        res = (rec.get("result") or "")
        trace = rec.get("trace") or ""
        spiral = trace.count("do something DIFFERENT") >= 3
        ok = (rec.get("status") == "done" and "DEMO-88" in res
              and not spiral)
        results.append(("fills the form once and finishes", ok,
                        f"status={rec.get('status')} result={res[:110]!r}"))

        ctx.close()
    srv.shutdown()
    failed = [r for r in results if not r[1]]
    for name, ok, note in results:
        print(f"  {'ok  ' if ok else 'FAIL'} {name} — {note}")
    print(f"agent identity chrome battery: "
          f"{len(results) - len(failed)}/{len(results)}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
