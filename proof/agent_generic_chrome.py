"""Real-Chrome battery for a GENERIC, non-restaurant errand — the class of
work the owner actually means by "a real job": find the contact form on a
company site (it is behind a link, not on the landing page), fill it with
the owner's real details and his own words, and submit. No booking, no
restaurant, no date widget — navigation, form filling, and completion
verification on an arbitrary site shape.
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
PORT = 8784

HOME = """<!doctype html><html><head><title>Northwind Tools</title></head>
<body>
<h1>Northwind Tools — industrial supply</h1>
<p>Quality equipment since 1987.</p>
<a href="/about">About us</a> | <a href="/contact">Contact</a> |
<a href="/careers">Careers</a>
</body></html>"""

CONTACT = """<!doctype html><html><head><title>Contact us</title></head>
<body>
<h2>Contact Northwind Tools</h2>
<label>Your name <input id="nm"></label>
<label>Email <input id="em" type="email"></label>
<label>Message <textarea id="msg"></textarea></label>
<button onclick="send()">Send message</button>
<div id="out"></div>
<script>
function send(){
  const v = id => document.getElementById(id).value.trim();
  if (!v('nm') || !v('em') || !v('msg')) {
    document.getElementById('out').textContent = 'All fields are required.';
    return; }
  document.getElementById('out').textContent =
    'Message sent — reference #NW-311. We reply within 2 business days.';
}
</script></body></html>"""

OTHER = """<!doctype html><html><body><h2>{}</h2>
<a href="/">Back home</a></body></html>"""


class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        if self.path.startswith("/contact"):
            body = CONTACT
        elif self.path == "/":
            body = HOME
        else:
            body = OTHER.format(self.path.strip("/").title())
        self.wfile.write(body.encode())

    def log_message(self, *a):
        pass


def clear_jobs():
    for it in httpx.get(f"{BASE}/api/collections/jobs/records",
                        params={"perPage": 200}).json()["items"]:
        httpx.delete(f"{BASE}/api/collections/jobs/records/{it['id']}")


def main():
    key = os.environ.get("OPENROUTER_API_KEY")
    assert key, "need OPENROUTER_API_KEY in env"
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    clear_jobs()
    results = []
    message = ("Do you stock the DW-450 drill press, and what is the "
               "current lead time?")
    scope = (f'Task: ask Northwind Tools whether they stock the DW-450 '
             f'drill press and the lead time, via their contact form. '
             f'Message, in their words: "{message}". They said: "yes".')
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            "/tmp/anticipy_generic_profile", headless=True,
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

        job = httpx.post(f"{BASE}/api/collections/jobs/records", json={
            "goal": ("Send Northwind Tools a message through their website "
                     "contact form asking whether they stock the DW-450 "
                     "drill press and the lead time"),
            "status": "queued",
            "params": json.dumps({
                "authorized": True, "approved_scope": scope,
                "message": message,
                "start_url": f"http://127.0.0.1:{PORT}/"}),
            "device_id": "anticipy-pendant-0001"}).json()
        deadline = time.time() + 240
        rec = {}
        while time.time() < deadline:
            time.sleep(3)
            rec = httpx.get(
                f"{BASE}/api/collections/jobs/records/{job['id']}").json()
            if rec.get("status") in ("done", "failed", "needs_user",
                                     "awaiting_confirm", "cancelled"):
                break
        res = rec.get("result") or ""
        trace = rec.get("trace") or ""
        # Proof of the deed, not of the wording: the run must end done, the
        # trace must show the form actually submitted from the contact page
        # (the done-verifier only passes "message sent" claims when the
        # page's own confirmation is showing).
        submitted = '"action":"click"' in trace and "/contact" in trace
        ok = (rec.get("status") == "done" and submitted
              and "sent" in res.lower())
        results.append(("finds the contact page behind a link, fills and "
                        "sends", ok,
                        f"status={rec.get('status')} result={res[:110]!r}"))
        ctx.close()
    srv.shutdown()
    failed = [r for r in results if not r[1]]
    for name, ok, note in results:
        print(f"  {'ok  ' if ok else 'FAIL'} {name} — {note}")
    print(f"agent generic chrome battery: "
          f"{len(results) - len(failed)}/{len(results)}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
