"""Real-Chrome battery for frame-aware mapping: the unpacked extension drives
a LOCAL page whose reservation widget lives INSIDE AN IFRAME (nothing real is
ever booked).

The live 2026-08-11 failure shape: earls.ca's "Make a Reservation" opens an
embedded reservation iframe. A mapper that only reads the top document cannot
see the date/party/time controls or the book button, so the agent re-opened
the widget for 60 steps and "refused to press book".

Two scenarios:
  1. the widget (date, time, party selects + the book button) is entirely
     inside an iframe -> the agent must set the fields and press the button;
  2. control: the same widget inline (regression for the non-iframe path).
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
PORT = 8779

WIDGET = """<!doctype html><html><head><title>Reserve</title></head><body>
<h2>Reserve a table</h2>
<label>Party size <select id="p"><option>1 person</option>
<option selected>2 people</option><option>3 people</option></select></label>
<label>Date <select id="d"><option selected>Mon Aug 10</option>
<option>Tue Aug 11</option><option>Wed Aug 12</option></select></label>
<label>Time <select id="t"><option>11:30 AM</option><option>12:00 PM</option>
<option selected>6:30 PM</option><option>7:00 PM</option></select></label>
<button id="go" onclick="done()">Find a table</button>
<div id="out"></div>
<script>
function done(){
  document.getElementById('out').textContent =
    'Reservation confirmed for ' + document.getElementById('p').value +
    ' on ' + document.getElementById('d').value +
    ' at ' + document.getElementById('t').value + '. Confirmation #DEMO-77.';
}
</script></body></html>"""

FRAMED = """<!doctype html><html><head><title>Demo Bistro</title></head><body>
<h1>Demo Bistro</h1><p>Book with our reservation partner below.</p>
<iframe src="/widget" width="600" height="400" title="Reservations"></iframe>
</body></html>"""


class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = (WIDGET if self.path.startswith("/widget") else FRAMED).encode()
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
    scope = ('Task: Book lunch at the demo bistro for tomorrow (Tue Aug 11) '
             'at noon, party of 2. They said: "yes". Heard originally: lunch '
             'tomorrow around noon, the demo bistro')
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            "/tmp/anticipy_iframe_profile", headless=True,
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

        # 1. the whole widget lives inside an iframe
        job = queue("Book lunch at the demo bistro for tomorrow at noon",
                    {"authorized": True, "approved_scope": scope,
                     "time": "noon", "party_size": "2",
                     "start_url": f"http://127.0.0.1:{PORT}/"})
        rec = watch(job["id"])
        res = (rec.get("result") or "")
        ok = (rec.get("status") == "done" and "12:00" in res
              and "Aug 11" in res)
        results.append(("operates the widget INSIDE the iframe", ok,
                        f"status={rec.get('status')} result={res[:110]!r}"))

        # 2. control: same widget inline (the non-iframe path still works)
        clear_jobs()
        job = queue("Book lunch at the demo bistro for tomorrow at noon",
                    {"authorized": True, "approved_scope": scope,
                     "time": "noon", "party_size": "2",
                     "start_url": f"http://127.0.0.1:{PORT}/widget"})
        rec = watch(job["id"])
        res = (rec.get("result") or "")
        ok = (rec.get("status") == "done" and "12:00" in res
              and "Aug 11" in res)
        results.append(("inline widget still works (control)", ok,
                        f"status={rec.get('status')} result={res[:110]!r}"))

        ctx.close()
    srv.shutdown()
    failed = [r for r in results if not r[1]]
    for name, ok, note in results:
        print(f"  {'ok  ' if ok else 'FAIL'} {name} — {note}")
    print(f"agent iframe chrome battery: "
          f"{len(results) - len(failed)}/{len(results)}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
