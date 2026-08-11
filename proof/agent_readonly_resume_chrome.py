"""Real-Chrome battery for the two 2026-08-11 production failures of job
9vw02ts9cd4h7ge (nothing real is ever booked):

  1. READONLY PICKER: the site's date field is readonly and only its own
     picker can set it. Live, the agent wrote "Aug 12" into it ten times
     while the site snapped it back to Aug 11, then stalled. Now the map
     labels the field, the executor refuses the direct write, and the run
     must finish by clicking the picker.

  2. PARKED-TAB RESUME: a run that stops needs_user (an OTP) must resume in
     the SAME tab. The page keeps its session in a JS variable that a fresh
     tab cannot have — completion after resume proves the tab was reused.
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
PORT = 8783

PICKER = """<!doctype html><html><head><title>Reserve a table</title></head>
<body>
<h2>Reserve — party of 3</h2>
<label>Date <input id="date" readonly value="Aug 11, 2026"
  onclick="document.getElementById('pick').style.display='block'"></label>
<div id="pick" style="display:none">
  <button onclick="setD('Aug 11, 2026')">Aug 11, 2026</button>
  <button onclick="setD('Aug 12, 2026')">Aug 12, 2026</button>
  <button onclick="setD('Aug 13, 2026')">Aug 13, 2026</button>
</div>
<button id="go" onclick="done()">Reserve</button>
<div id="out"></div>
<script>
function setD(v){ document.getElementById('date').value=v;
  document.getElementById('pick').style.display='none'; }
function done(){
  const d = document.getElementById('date').value;
  document.getElementById('out').textContent = (d === 'Aug 12, 2026')
    ? 'Reserved for Aug 12, 2026, party of 3. Confirmation #PICK-42.'
    : 'Please choose the correct date first (currently ' + d + ').';
}
</script></body></html>"""

OTP = """<!doctype html><html><head><title>Confirm booking</title></head>
<body>
<h2>Confirm your booking</h2>
<p id="stage">We texted a verification code to your phone. Enter it to
finish the booking for Aug 12 at 2 PM, party of 3.</p>
<label>Verification code <input id="code"></label>
<button onclick="finish()">Confirm booking</button>
<div id="out"></div>
<script>
// The session only exists in THIS tab. A fresh tab has no session and the
// form rejects everything — exactly like a real OTP flow.
var SESSION = 'live-' + Math.random().toString(36).slice(2);
function finish(){
  if (!SESSION) { document.getElementById('out').textContent =
    'Session expired — start over.'; return; }
  var v = document.getElementById('code').value.trim();
  document.getElementById('out').textContent = (v === '774421')
    ? 'Booking confirmed for Aug 12 at 2 PM. Confirmation #OTP-77.'
    : 'That code is not correct.';
}
</script></body></html>"""


class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write((OTP if self.path.startswith("/otp")
                          else PICKER).encode())

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
    scope = ('Task: book a table for Aug 12 at 2 PM, party of 3. '
             'They said: "yes".')
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            "/tmp/anticipy_ro_resume_profile", headless=True,
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
                 keyFetchedAt: Date.now(), owner: "batt",
                 ownerProfile: {first_name: "Omar", last_name: "Test",
                                email: "omar@example.com",
                                phone: "+16045550000"} })""",
            [BASE, key,
             os.environ.get("ANTICIPY_MODEL", "google/gemini-2.5-flash")])
        time.sleep(2)

        # 1. readonly picker — must finish through the picker, no write loop
        job = queue("Reserve the table for Aug 12, 2026, party of 3",
                    {"authorized": True, "approved_scope": scope,
                     "date": "Aug 12, 2026", "party_size": "3",
                     "start_url": f"http://127.0.0.1:{PORT}/"})
        rec = watch(job["id"])
        res = rec.get("result") or ""
        trace = rec.get("trace") or ""
        hammering = trace.count('it did not take') >= 3
        ok = rec.get("status") == "done" and "PICK-42" in res \
            and not hammering
        results.append(("readonly date set through the site's picker", ok,
                        f"status={rec.get('status')} result={res[:100]!r}"))

        # 2. OTP park + resume in the SAME tab
        clear_jobs()
        job = queue("Finish the booking for Aug 12 at 2 PM for 3 people",
                    {"authorized": True, "approved_scope": scope,
                     "start_url": f"http://127.0.0.1:{PORT}/otp"})
        rec = watch(job["id"])
        params = json.loads(rec.get("params") or "{}")
        parked = (rec.get("status") == "needs_user"
                  and "code" in (rec.get("result") or "").lower()
                  and params.get("resume_tab") is not None)
        results.append(("parks needs_user asking for the code, tab saved",
                        parked,
                        f"status={rec.get('status')} "
                        f"resume_tab={params.get('resume_tab')!r}"))
        if parked:
            # the owner texts the code; the job re-queues with it
            params["verification_code"] = "774421"
            httpx.patch(
                f"{BASE}/api/collections/jobs/records/{job['id']}",
                json={"status": "queued", "params": json.dumps(params)})
            rec = watch(job["id"])
            res = rec.get("result") or ""
            ok = rec.get("status") == "done" and "OTP-77" in res
            results.append(("resumes in the parked tab and completes "
                            "(a fresh tab could not have)", ok,
                            f"status={rec.get('status')} "
                            f"result={res[:100]!r}"))
        ctx.close()
    srv.shutdown()
    failed = [r for r in results if not r[1]]
    for name, ok, note in results:
        print(f"  {'ok  ' if ok else 'FAIL'} {name} — {note}")
    print(f"agent readonly+resume chrome battery: "
          f"{len(results) - len(failed)}/{len(results)}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()


