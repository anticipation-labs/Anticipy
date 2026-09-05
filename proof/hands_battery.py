"""THE HANDS, WATCHED. The real extension, in a real Chrome, on the real
production model, driving pages built to reproduce Omar's ACTUAL failures.

Not a unit test. Every scenario here is a live failure he watched happen:

  readonly_date   the Earls date field is readonly — the site only sets it
                  from its own calendar popup. It kept writing the date in
                  and the site kept snapping it back.
  site_defaults   the widget opens on today/6:30pm; the task says tomorrow
                  at noon. Defaults are fields to SET, not news to report.
  no_identity     no name on file. It coined "Anticipation Labs" as a last
                  name from the email address and booked under a fake one.
  unnamed_branch  the task never said WHICH location. It toured Winnipeg.
  otp_resume      the site texts a code. It parks — and the resume used to
                  open a NEW tab, losing the session, the filled form and
                  the code's own validity.
  autocomplete    type, then PICK a suggestion. It retyped forever.
  general_form    NOT a restaurant. A support ticket, to prove the machinery
                  is not reservation-shaped.

Each scenario asserts on the SITE's own final state (what actually happened
in the page), never on the agent's self-report — an agent that says "done"
proves nothing.

TWO WAYS TO RUN IT, and only one of them measures anything today.

  --rig   (the default whenever PocketBase answers on 127.0.0.1:8090)
          The jobs go to the LOCAL RIG — the repo's own PocketBase with this
          tree's hooks (sh proof/local_rig.sh up) — and are run by the arm
          proof/chrome_arm.mjs stood up: a Chrome for Testing that registered
          through the real hooks, was paired to the rig's owner, and is handed
          the real browser model through the real /agent/llm proxy. Nothing in
          that chain is a mock; proof/extension_smoke.mjs proves it end to end
          in two minutes and this file queues rows the way that smoke does.
          The fixture site below still runs here on :8792, on loopback, where
          the arm's Chrome can reach it.

              sh proof/local_rig.sh up
              node proof/chrome_arm.mjs up
              python3 proof/hands_battery.py [--rig] [name ...]

  --fake  The ORIGINAL harness: a stand-in backend on :8791 (class BackendH)
          and Playwright's Chromium. It is DEAD against extension 0.13.0 and
          has been since the workflow law landed: it mints rows without
          `workflow_id` and the embedded `params._workflow` plan, so
          claimJob's `isWorkflowJob` refuses every one of them and every
          scenario sits `status=queued` for its whole 300s. It also imitates
          PocketBase's filter/PATCH semantics loosely and serves no
          /api/health (harmless — only onboarding.js and popup.js probe that,
          the worker never gates on it). Kept reachable so nothing is lost,
          and so the two can be diffed; do not extend it.

              OPENROUTER_API_KEY=... python3 proof/hands_battery.py --fake [name ...]

Flags: --rig --fake --base=URL --owner-ref=ID --owner=ID --arm-port=N
       --wait=SECONDS (per-scenario watch, default 300)
"""
from __future__ import annotations

import hashlib
import http.server
import json
import os
import queue
import re
import socketserver
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EXT = os.path.join(ROOT, "extension")

BACKEND_PORT = 8791
SITE_PORT = 8792
BACKEND = f"http://127.0.0.1:{BACKEND_PORT}"
SITE = f"http://127.0.0.1:{SITE_PORT}"

MODEL = os.environ.get("ANTICIPY_MODEL", "google/gemini-2.5-flash")
VISION_MODEL = os.environ.get("ANTICIPY_VISION_MODEL", "google/gemini-2.5-flash")
OWNER = "battery-owner"

# ---------------------------------------------------------------- flags
# A misspelled flag must not read as a default (proof/extension_smoke.mjs:61).
KNOWN_FLAGS = ("rig", "fake", "base", "owner-ref", "owner", "arm-port", "wait")


def _arg(name, fallback=None):
    for a in sys.argv[1:]:
        if a.startswith(f"--{name}="):
            return a[len(name) + 3:]
    return fallback


def _flag(name):
    return f"--{name}" in sys.argv[1:]


for _a in sys.argv[1:]:
    if _a.startswith("--") and _a[2:].split("=")[0] not in KNOWN_FLAGS:
        sys.exit(f"unknown flag {_a}. Known: {' '.join('--' + k for k in KNOWN_FLAGS)}")

# "rig" or "fake"; decided in main() once the rig has (or has not) answered.
MODE = [None]
WATCH_S = int(_arg("wait", "300"))

# ---------------------------------------------------------------- the site
# Server-side state, so a scenario can assert what the SITE believes happened
# rather than what the agent claims. This is the whole point.
SITE_STATE = {}
SITE_LOCK = threading.Lock()


def reset_site():
    with SITE_LOCK:
        SITE_STATE.clear()
        SITE_STATE.update({
            "booking": None, "ticket": None, "otp_sent": False,
            "otp_verified": False, "session": 0, "submits": [],
        })


PAGE_HEAD = """<!doctype html><html><head><meta charset=utf-8>
<title>%(title)s</title><style>
body{font-family:system-ui;margin:2rem;max-width:640px}
label{display:block;margin:.6rem 0}
input,select{padding:.4rem;font-size:1rem;min-width:14rem}
button{padding:.5rem 1rem;font-size:1rem;margin-top:.8rem}
.cal{position:fixed;top:20%%;left:30%%;background:#fff;border:2px solid #333;
padding:1rem;box-shadow:0 4px 24px rgba(0,0,0,.3);z-index:99}
.cal button{margin:.2rem;min-width:5.5rem}
#out{margin-top:1.2rem;padding:.8rem;background:#eef;font-weight:600}
</style></head><body>"""


def page(title, body):
    return (PAGE_HEAD % {"title": title}) + body + "</body></html>"


# --- readonly date: the field can ONLY be set by clicking it open ----------
READONLY_DATE = page("Demo Bistro — Reserve", """
<h1>Demo Bistro</h1><h2>Reserve a table</h2>
<label>Date <input id="d" readonly value="Mon Aug 10" placeholder="Pick a date"></label>
<label>Time <select id="t">
  <option>11:30 AM</option><option>12:00 PM</option><option>1:00 PM</option>
  <option>1:30 PM</option><option selected>6:30 PM</option><option>7:00 PM</option>
</select></label>
<label>Party <select id="p">
  <option>1 person</option><option selected>2 people</option>
  <option>3 people</option><option>4 people</option></select></label>
<button id="go">Find a table</button>
<div id="out"></div>
<script>
const d = document.getElementById('d');
d.addEventListener('click', () => {
  if (document.querySelector('.cal')) return;
  const c = document.createElement('div');
  c.className = 'cal';
  c.innerHTML = '<div>August 2026</div>';
  ['Mon Aug 10','Tue Aug 11','Wed Aug 12','Thu Aug 13'].forEach(day => {
    const b = document.createElement('button');
    b.textContent = day;
    b.onclick = (e) => { e.preventDefault(); d.value = day; c.remove(); };
    c.appendChild(b);
  });
  document.body.appendChild(c);
});
// The site owns this field. Anything written directly is reverted, exactly
// like a real date-picker widget backed by its own state.
setInterval(() => {
  const ok = ['Mon Aug 10','Tue Aug 11','Wed Aug 12','Thu Aug 13'];
  if (!ok.includes(d.value)) d.value = 'Mon Aug 10';
}, 150);
document.getElementById('go').onclick = () => {
  const payload = {date: d.value, time: document.getElementById('t').value,
                   party: document.getElementById('p').value};
  fetch('/booked', {method:'POST', body: JSON.stringify(payload)});
  document.getElementById('out').textContent =
    'Confirmed: ' + payload.party + ' on ' + payload.date + ' at ' +
    payload.time + '. Confirmation #DEMO-77.';
};
</script>""")

# --- identity form: requires a first AND last name ------------------------
IDENTITY_FORM = page("Demo Bistro — Your details", """
<h1>Almost done</h1><p>Table held for 5 minutes. Who is it under?</p>
<label>First name <input id="fn" required></label>
<label>Last name <input id="ln" required></label>
<label>Email <input id="em" type="email" required></label>
<label>Phone <input id="ph" required></label>
<button id="go">Confirm reservation</button>
<div id="out"></div>
<script>
document.getElementById('go').onclick = () => {
  const p = {first: fn.value, last: ln.value, email: em.value, phone: ph.value};
  if (!p.first || !p.last) { out.textContent = 'First and last name are required.'; return; }
  fetch('/booked', {method:'POST', body: JSON.stringify(p)});
  out.textContent = 'Confirmed for ' + p.first + ' ' + p.last + '. #DEMO-88';
};
</script>""")

# --- branch chooser: many locations, task names none ----------------------
BRANCHES = page("Demo Bistro — Locations", """
<h1>Demo Bistro — 6 locations</h1>
<ul>
<li><a href="/branch?b=Winnipeg+Main+St">Winnipeg — Main St</a></li>
<li><a href="/branch?b=Calgary+Stephen+Ave">Calgary — Stephen Ave</a></li>
<li><a href="/branch?b=Toronto+Front+St">Toronto — Front St</a></li>
<li><a href="/branch?b=West+Vancouver+Marine+Dr">West Vancouver — Marine Dr</a></li>
<li><a href="/branch?b=Vancouver+Robson">Vancouver — Robson</a></li>
<li><a href="/branch?b=Halifax+Barrington">Halifax — Barrington</a></li>
</ul>""")

# --- OTP: submit demands a code the site "texts" --------------------------
OTP_FORM = page("Demo Bistro — Confirm", """
<h1>Confirm your reservation</h1>
<p>Tue Aug 11, 1:30 PM, 3 people.</p>
<label>Name <input id="nm" value=""></label>
<button id="send">Text me a code</button>
<div id="stage"></div>
<div id="out"></div>
<script>
document.getElementById('send').onclick = async () => {
  await fetch('/otp/send', {method:'POST'});
  document.getElementById('stage').innerHTML =
    '<p>We texted a 6-digit code to your phone.</p>' +
    '<label>Verification code <input id="code"></label>' +
    '<button id="verify">Verify and book</button>';
  document.getElementById('verify').onclick = async () => {
    const r = await fetch('/otp/verify?code=' +
      encodeURIComponent(document.getElementById('code').value));
    document.getElementById('out').textContent = await r.text();
  };
};
</script>""")

# --- autocomplete: must pick a suggestion ---------------------------------
AUTOCOMPLETE = page("Demo Travel", """
<h1>Demo Travel</h1>
<label>Destination <input id="q" autocomplete="off" placeholder="City"></label>
<div id="sugg"></div>
<div id="out"></div>
<script>
const CITIES = ['Vancouver (YVR)','Vancouver WA (VUO)','Vancouverville (VVV)',
                'Victoria (YYJ)','Toronto (YYZ)'];
let chosen = null;
q.addEventListener('input', () => {
  chosen = null;
  const v = q.value.trim().toLowerCase();
  sugg.innerHTML = '';
  if (!v) return;
  CITIES.filter(c => c.toLowerCase().includes(v)).forEach(c => {
    const b = document.createElement('button');
    b.textContent = c;
    b.onclick = (e) => { e.preventDefault(); chosen = c; q.value = c;
      sugg.innerHTML = ''; out.textContent = 'Selected: ' + c;
      fetch('/picked', {method:'POST', body: JSON.stringify({city:c})}); };
    sugg.appendChild(b);
  });
});
// Typing alone is never a choice — the site only accepts a picked suggestion.
</script>""")

# --- a general, non-restaurant task ---------------------------------------
SUPPORT_FORM = page("Acme Support", """
<h1>Acme — Contact support</h1>
<label>Your email <input id="em" type="email" required></label>
<label>Category <select id="cat">
  <option value="">Choose…</option><option>Billing</option>
  <option>Bug report</option><option>Account access</option></select></label>
<label>Order number <input id="ord"></label>
<label>Message <textarea id="msg" rows=4 cols=40></textarea></label>
<button id="go">Submit ticket</button>
<div id="out"></div>
<script>
document.getElementById('go').onclick = () => {
  if (!em.value || !cat.value) { out.textContent='Email and category required.'; return; }
  fetch('/ticket', {method:'POST', body: JSON.stringify(
    {email:em.value, cat:cat.value, order:ord.value, msg:msg.value})});
  out.textContent = 'Ticket received. Reference #ACME-4021.';
};
</script>""")

# --- a readonly NATIVE date input: the case the map used to leave unlabelled
# because <input type=date> returns from its own branch before the readonly
# hint is ever appended. The site refuses direct writes, exactly like a real
# picker-backed field.
NATIVE_DATE = page("Demo Clinic — Book", """
<h1>Demo Clinic</h1>
<label>Appointment date <input id="d" type="date" readonly value="2026-08-10"></label>
<label>Time <select id="t"><option selected>9:00 AM</option>
  <option>2:00 PM</option><option>3:30 PM</option></select></label>
<button id="pick">Choose a date</button>
<div id="cal"></div>
<button id="go">Book appointment</button>
<div id="out"></div>
<script>
// A real picker-backed field opens on the field itself as well as its button.
const openCal = () => {
  cal.innerHTML = '';
  ['2026-08-11','2026-08-12','2026-08-13'].forEach(v => {
    const b = document.createElement('button');
    b.textContent = v;
    b.onclick = (e) => { e.preventDefault(); d.value = v; cal.innerHTML = ''; };
    cal.appendChild(b);
  });
};
document.getElementById('pick').onclick = openCal;
d.addEventListener('click', openCal);
setInterval(() => {
  const ok = ['2026-08-10','2026-08-11','2026-08-12','2026-08-13'];
  if (!ok.includes(d.value)) d.value = '2026-08-10';
}, 150);
document.getElementById('go').onclick = () => {
  fetch('/booked', {method:'POST', body: JSON.stringify(
    {date: d.value, time: t.value})});
  out.textContent = 'Booked ' + d.value + ' at ' + t.value + '. #CLINIC-12';
};
</script>""")

ROUTES = {
    "/native-date": NATIVE_DATE,
    "/readonly-date": READONLY_DATE,
    "/identity": IDENTITY_FORM,
    "/branches": BRANCHES,
    "/otp": OTP_FORM,
    "/autocomplete": AUTOCOMPLETE,
    "/support": SUPPORT_FORM,
}


class SiteH(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, body, ctype="text/html", code=200):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        p = urllib.parse.urlparse(self.path)
        if p.path in ROUTES:
            return self._send(ROUTES[p.path])
        if p.path == "/branch":
            b = urllib.parse.parse_qs(p.query).get("b", [""])[0]
            with SITE_LOCK:
                SITE_STATE.setdefault("visited_branches", []).append(b)
            return self._send(page("Branch", f"<h1>{b}</h1>"
                                   f"<p>Reserve at our {b} location.</p>"
                                   f"<button id='go'>Book here</button>"
                                   f"<div id='out'></div><script>"
                                   f"go.onclick=()=>{{fetch('/booked',{{method:'POST',"
                                   f"body:JSON.stringify({{branch:'{b}'}})}});"
                                   f"out.textContent='Booked at {b}. #DEMO-99';}}"
                                   f"</script>"))
        if p.path == "/otp/verify":
            code = urllib.parse.parse_qs(p.query).get("code", [""])[0]
            with SITE_LOCK:
                if not SITE_STATE.get("otp_sent"):
                    return self._send("No code was requested.", "text/plain")
                if code.strip() == "482913":
                    SITE_STATE["otp_verified"] = True
                    SITE_STATE["booking"] = {"via": "otp"}
                    return self._send(
                        "Reservation confirmed. Confirmation #DEMO-OTP-55.",
                        "text/plain")
                return self._send(f"That code ({code}) is not right.", "text/plain")
        return self._send("not found", "text/plain", 404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n).decode() if n else "{}"
        p = urllib.parse.urlparse(self.path).path
        with SITE_LOCK:
            if p == "/booked":
                try:
                    SITE_STATE["booking"] = json.loads(raw)
                except Exception:
                    SITE_STATE["booking"] = {"raw": raw}
                SITE_STATE["submits"].append(SITE_STATE["booking"])
            elif p == "/ticket":
                SITE_STATE["ticket"] = json.loads(raw)
            elif p == "/picked":
                SITE_STATE["picked"] = json.loads(raw)
            elif p == "/otp/send":
                SITE_STATE["otp_sent"] = True
        return self._send("ok", "text/plain")

    def log_message(self, *a):
        pass


# --------------------------------------------------------------- the fake
# The original stand-in for production PocketBase. DEAD against 0.13.0 — see
# the header — and reachable only with --fake. Exactly the endpoints
# extension/background.js used to call, with roughly the same shapes.
JOBS = {}
AGENTS = {}
DB_LOCK = threading.Lock()
JOB_SEQ = [0]
EVENTS = queue.Queue()


def _fake_make_job(goal, params, owner=OWNER, lane=""):
    with DB_LOCK:
        JOB_SEQ[0] += 1
        jid = f"job{JOB_SEQ[0]:04d}"
        JOBS[jid] = {
            "id": jid, "goal": goal, "status": "queued", "owner": owner,
            "lane": lane, "params": json.dumps(params), "result": "",
            "trace": "", "attempts": 0, "claimed_by": "", "claimed_at": None,
            "created": time.strftime("%Y-%m-%d %H:%M:%S"),
            "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
    EVENTS.put(jid)
    return jid


class BackendH(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _json(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        if u.path == "/agent/key":
            return self._json({
                "openrouter_key": os.environ["OPENROUTER_API_KEY"],
                "model": MODEL, "vision_model": VISION_MODEL,
                "service_token": "", "owner": OWNER_PROFILE[0],
            })
        if u.path == "/api/collections/jobs/records":
            filt = q.get("filter", [""])[0]
            with DB_LOCK:
                items = [j for j in JOBS.values()
                         if (('status="queued"' in filt and j["status"] == "queued")
                             or ('status="running"' in filt and j["status"] == "running"))
                         and j["owner"] in (OWNER, "")
                         and j["lane"] != "research"]
                items.sort(key=lambda j: j["id"])
            return self._json({"items": items, "totalItems": len(items)})
        if u.path.startswith("/api/collections/jobs/records/"):
            jid = u.path.rsplit("/", 1)[-1]
            with DB_LOCK:
                if jid not in JOBS:
                    return self._json({"message": "not found"}, 404)
                return self._json(JOBS[jid])
        if u.path == "/api/realtime":
            # The extension's SSE path. Keeping it open but silent is enough:
            # the 5s alarm is the real driver and this must not 404-loop.
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            try:
                self.wfile.write(b'event:PB_CONNECT\ndata:{"clientId":"c1"}\n\n')
                self.wfile.flush()
                deadline = time.time() + 600
                while time.time() < deadline:
                    time.sleep(15)
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
            except Exception:
                pass
            return
        return self._json({"message": "not found"}, 404)

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n).decode() or "{}") if n else {}
        if u.path == "/api/collections/agents/records":
            rid = f"agent{len(AGENTS) + 1}"
            rec = {**body, "id": rid, "owner": OWNER, "paired": True}
            AGENTS[rid] = rec
            return self._json(rec)
        if u.path == "/api/realtime":
            return self._json({"ok": True})
        return self._json({"message": "not found"}, 404)

    def do_PATCH(self):
        u = urllib.parse.urlparse(self.path)
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n).decode() or "{}") if n else {}
        if u.path.startswith("/api/collections/agents/records/"):
            rid = u.path.rsplit("/", 1)[-1]
            rec = AGENTS.setdefault(rid, {"id": rid})
            rec.update(body)
            rec["owner"] = OWNER
            rec["paired"] = True
            return self._json(rec)
        if u.path.startswith("/api/collections/jobs/records/"):
            jid = u.path.rsplit("/", 1)[-1]
            with DB_LOCK:
                if jid not in JOBS:
                    return self._json({"message": "not found"}, 404)
                JOBS[jid].update(body)
                JOBS[jid]["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
                return self._json(JOBS[jid])
        return self._json({"message": "not found"}, 404)

    def log_message(self, *a):
        pass


class Threaded(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


# Owner profile the backend hands the extension. Mutated per scenario: the
# invented-identity test needs a profile with NO name on it. In rig mode the
# same values are written onto the rig's own owner_profile row (that is what
# /agent/key reads, at the start of every run) and the row is restored after.
FULL_PROFILE = {
    "first_name": "Omar", "last_name": "Ebrahim",
    "email": "omar@anticipy.ai", "phone": "+16047245161", "facts": "{}",
}
OWNER_PROFILE = [dict(FULL_PROFILE)]
NO_NAME_PROFILE = {
    "first_name": "", "last_name": "",
    "email": "omar@anticipy.ai", "phone": "+16047245161", "facts": "{}",
}
PROFILE_FIELDS = ("first_name", "last_name", "email", "phone")


# ---------------------------------------------------------------- the rig
# Everything below talks to the real PocketBase the way the brain and
# proof/extension_smoke.mjs do. No auth header beyond the one smoke sends:
# the rig runs with no ANTICIPY_SERVICE_TOKEN (guard.pb.js falls through), so
# the token — if the environment happens to carry one — is sent and ignored.
#
# LOOPBACK ONLY. `.env.local` carries ANTICIPY_PB pointing at PRODUCTION, and
# the documented way to run this sources that file. So the base is never read
# from the environment, and a --base that is not loopback is a refusal: this
# file queues approved, world-touching work and lets a browser act on it.
RIG = {
    "base": (_arg("base", "http://127.0.0.1:8090") or "").rstrip("/"),
    "owner_ref": "",
    "owner": _arg("owner", "local-dev"),
    "arm_port": int(_arg("arm-port", "29344")),
    "profile_id": "",
    "profile_original": None,
    "ext_id": "",
}
ARM = lambda: f"http://127.0.0.1:{RIG['arm_port']}"  # noqa: E731
# Job ids this scenario minted, so tidy and the trace dump know what is ours.
SCENARIO_JOBS = []
TERMINAL = ("done", "failed", "needs_user", "awaiting_confirm", "cancelled")
SETTLED = ("done", "failed", "cancelled")


def _http(method, url, body=None, timeout=15, token=False):
    data = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json"}
    # Only ever to the rig. The devtools port is not a place a service token
    # should be seen, even on loopback.
    tok = os.environ.get("ANTICIPY_SERVICE_TOKEN") if token else ""
    if tok:
        headers["X-Anticipy-Token"] = tok
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            text = r.read().decode("utf-8", "replace")
            status = r.status
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", "replace")
        status = e.code
    except (urllib.error.URLError, OSError) as e:
        return 0, None, str(e)
    try:
        js = json.loads(text) if text else None
    except Exception:
        js = None
    return status, js, text


def rig(method, path, body=None):
    return _http(method, RIG["base"] + path, body, token=True)


def rig_row(jid):
    st, js, text = rig("GET", f"/api/collections/jobs/records/{jid}")
    if st != 200 or not isinstance(js, dict):
        raise RuntimeError(f"GET job {jid} -> {st} {text[:160]}")
    return js


def _canonical(value):
    # brain/workflow.py:_canonical, byte for byte.
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value):
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def stamp():
    # Python's datetime.isoformat(), which is what brain/workflow.py writes.
    return datetime.now(timezone.utc).isoformat()


def _plan_digests(plan):
    """Plan.scope_digest / Plan.effect_key from brain/workflow.py."""
    scope = {
        "plan_id": plan["plan_id"], "version": plan["version"],
        "goal": plan["goal"], "facts": dict(plan["facts"]),
        "consequence": plan["consequence"],
    }
    if plan.get("authority_text"):
        scope["authority_text"] = plan["authority_text"]
    return _digest(scope), _digest({"owner_ref": plan["owner_ref"], **scope})


def _approval(plan, owner_words):
    """brain/workflow.py:approve — bound to THIS plan id, version and scope."""
    return {
        "plan_id": plan["plan_id"],
        "plan_version": plan["version"],
        "scope_digest": plan["scope_digest"],
        "owner_words": owner_words,
        "approved_at": stamp(),
        "gesture": None,
    }


def _job_fields(plan):
    """Plan.job_fields(): the PocketBase columns that mirror the embedded plan."""
    lease = plan.get("lease") or {}
    return {
        "workflow_id": plan["plan_id"],
        "workflow_version": plan["version"],
        "workflow_state": plan["state"],
        "consequence": plan["consequence"],
        "lineage_key": plan["lineage_key"],
        "effect_key": plan["effect_key"],
        "scope_digest": plan["scope_digest"],
        "approval": _canonical(plan["approval"]) if plan.get("approval") else "",
        "receipt": _canonical(plan["receipt"]) if plan.get("receipt") else "",
        "lease_token": lease.get("token", ""),
        "lease_until": lease.get("expires_at", ""),
        "source_event_ids": _canonical(list(plan["source_event_ids"])),
        "attempts": plan["attempts"],
        "status": {"queued": "queued", "cancelled": "cancelled"}.get(plan["state"], plan["state"]),
    }


# The scenario keys that are the job's own plumbing, not facts about the
# errand. Everything else a scenario passes (date, time, party_size, order
# number, category) is a FACT the brain would have put on the plan — and once a
# row carries _workflow, `ownerFactsFromParams` reads ONLY the plan's facts, so
# they have to live there or the hands never see them.
NOT_FACTS = ("task", "authorized", "approved_scope", "start_url")


def _rig_make_job(goal, params):
    task = str(params["task"])
    # The owner's words are the authority. In the fake, the hands measured every
    # action against approved_scope alone (there was no plan); here the same
    # string is the plan's authority_text, so what they measure against is
    # unchanged — and it is also the words the approval retains.
    authority = str(params.get("approved_scope") or task)
    facts = {k: str(v) for k, v in params.items() if k not in NOT_FACTS}
    plan_id = str(uuid.uuid4())
    lineage = f"hands-{plan_id[:8]}"
    now = stamp()
    plan = {
        "plan_id": plan_id,
        "owner_ref": RIG["owner_ref"],
        "lineage_key": lineage,
        "version": 1,
        "goal": task,
        "authority_text": authority,
        # World-touching: every scenario books, submits or picks. The extension
        # reads `params.authorized === true || consequence === "read_only"` for
        # its authority and `consequence === "read_only"` for its read-only
        # fence (background.js:1655-1656), so the approved booking needs
        # consequential + a version-bound approval, never read_only.
        "consequence": "consequential",
        "state": "queued",
        "facts": facts,
        "required": [],
        "source_event_ids": [lineage],
        "approval": None,
        "lease": None,
        "receipt": None,
        "attempts": 0,
        "reason": "approved by owner",
        "created_at": now,
        "updated_at": now,
    }
    plan["scope_digest"], plan["effect_key"] = _plan_digests(plan)
    plan["approval"] = _approval(plan, authority)
    body = {
        "goal": task,
        # A TEXT column: a nested object is stored as "" (smoke, step 6).
        "params": json.dumps({
            **params,
            "source": f"proof/hands_battery.py at {datetime.now(timezone.utc).isoformat()}",
            "_workflow": plan,
        }),
        "device_id": "anticipy",
        "owner": RIG["owner"],
        "owner_ref": RIG["owner_ref"],
        # NOT "research": that lane is hidden from the extension's poll.
        "lane": "",
        **_job_fields(plan),
    }
    st, js, text = rig("POST", "/api/collections/jobs/records", body)
    if st != 200 or not isinstance(js, dict) or not js.get("id"):
        hint = " (workflow_guard.pb.js refused the row)" if st == 409 else ""
        raise RuntimeError(f"POST job -> {st}{hint}: {text[:300]}")
    jid = js["id"]
    SCENARIO_JOBS.append(jid)
    print(f"       {_clock()}  {jid}  queued  goal={task[:70]!r}", flush=True)
    return jid


def _clock():
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def _rig_watch(jid, seconds):
    """Poll the row and say every status change out loud, with the clock, so a
    stall is readable: which state it sat in, for how long, and what the row
    said when it moved."""
    t0 = time.time()
    deadline = t0 + seconds
    # make_job already said "queued"; only CHANGES are news from here.
    last = ("queued", "")
    nudged = False
    row = rig_row(jid)
    while True:
        key = (row.get("status"), row.get("claimed_by") or "")
        if key != last:
            last = key
            extra = ""
            if row.get("status") == "running":
                extra = f"  claimed_by={str(row.get('claimed_by') or '')[:12]} attempt={row.get('attempts')}"
            if row.get("result"):
                extra += f"  result={str(row['result'])[:110]!r}"
            print(f"       {_clock()}  {jid}  {row.get('status')}{extra}  [+{int(time.time() - t0)}s]",
                  flush=True)
        if row.get("status") in TERMINAL:
            return row
        if time.time() >= deadline:
            print(f"       {_clock()}  {jid}  still {row.get('status')} after {seconds}s — giving up on it",
                  flush=True)
            return row
        # THE 30s ALARM FLOOR, and the arm that stops beating. chrome.alarms
        # will not repeat faster than every half minute, so 30s of `queued` is
        # normal. Past 45s it is not — and this headless arm has been seen to
        # stop heartbeating altogether after ~9 idle minutes. One nudge, the
        # same one a person gives by opening the setup page (chrome_arm.mjs
        # `up`), and it is SAID, so a claim time in the log is never mistaken
        # for one the alarm produced.
        if (not nudged and row.get("status") == "queued" and not row.get("claimed_by")
                and time.time() - t0 > 45):
            nudged = True
            why = arm_nudge()
            print(f"       {_clock()}  {jid}  not claimed after 45s — nudged the arm ({why})", flush=True)
        time.sleep(2)
        row = rig_row(jid)


def _rig_cancel(jid, why):
    """Cancel the way every other client must — columns and embedded plan move
    together — or workflow_guard.pb.js refuses it. Falls back to DELETE. This is
    smoke's tidy(). A queued browser job left behind is not litter; it fires
    later in a real Chrome."""
    row = rig_row(jid)
    if row.get("status") in SETTLED:
        return f"left as {row['status']} (it is the evidence)"
    try:
        params = json.loads(row.get("params") or "{}")
    except Exception:
        params = {}
    plan = {**(params.get("_workflow") or {}), "state": "cancelled", "lease": None,
            "attempts": int(row.get("attempts") or 0), "reason": why,
            "updated_at": stamp()}
    st, _, text = rig("PATCH", f"/api/collections/jobs/records/{jid}", {
        "status": "cancelled",
        "workflow_state": "cancelled",
        "workflow_version": int(row.get("workflow_version") or 1),
        "lease_token": "",
        "lease_until": "",
        "params": json.dumps({**params, "_workflow": plan}),
        "result": row.get("result") or why,
    })
    if st == 200:
        return f"cancelled (was {row['status']})"
    d, _, dtext = rig("DELETE", f"/api/collections/jobs/records/{jid}")
    if d in (200, 204):
        return f"deleted (cancel refused {st}: {text[:100]}; was {row['status']})"
    return (f"COULD NOT CLEAR — still {row['status']}; cancel {st}: {text[:100]}; "
            f"delete {d}: {dtext[:60]}. Clear it by hand at {RIG['base']}/_/")


def _rig_resume(jid, changes, owner_text):
    """The brain's resume of a parked run, from brain/conversation.py:_amend
    for a needs_user row: the answer lands in params, `needed` records what
    was asked, approved_scope grows the Q/A tail the hands read, and the plan
    is re-approved with the answer as a fact — brain/workflow.py:approve with
    `changes`: version+1, digests recomputed, approval re-bound to the new
    version and scope, attempts back to 0, state queued."""
    row = rig_row(jid)
    try:
        params = json.loads(row.get("params") or "{}")
    except Exception:
        params = {}
    plan = dict(params.get("_workflow") or {})
    if not plan:
        raise RuntimeError(f"resume: job {jid} carries no _workflow plan")
    need = (row.get("result") or params.get("needed") or "").strip()
    params.update(changes)
    if need and not params.get("needed"):
        params["needed"] = need[:300]
    if params.get("approved_scope"):
        params["approved_scope"] += (
            f' You stopped and asked: "{need}". '
            f'They answered: "{owner_text}" — that answer is final; act on it.')
    facts = dict(plan.get("facts") or {})
    facts.update({k: str(v) for k, v in changes.items()})
    plan.update({
        "version": int(plan.get("version") or 1) + 1,
        "facts": facts,
        "state": "queued",
        "attempts": 0,
        "lease": None,
        "receipt": None,
        "reason": "approved by owner",
        "updated_at": stamp(),
    })
    plan["scope_digest"], plan["effect_key"] = _plan_digests(plan)
    plan["approval"] = _approval(plan, owner_text)
    params["_workflow"] = plan
    body = {"status": "queued", "params": json.dumps(params), **_job_fields(plan)}
    st, _, text = rig("PATCH", f"/api/collections/jobs/records/{jid}", body)
    if st != 200:
        hint = " (workflow_guard.pb.js refused the resume)" if st == 409 else ""
        raise RuntimeError(f"resume PATCH -> {st}{hint}: {text[:300]}")
    print(f"       {_clock()}  {jid}  resumed as version {plan['version']} with the answer", flush=True)


def _rig_set_profile(profile):
    body = {k: profile.get(k, "") for k in PROFILE_FIELDS}
    st, _, text = rig("PATCH", f"/api/collections/owner_profile/records/{RIG['profile_id']}", body)
    if st != 200:
        raise RuntimeError(f"owner_profile PATCH -> {st}: {text[:200]}")


# ---------------------------------------------------------------- the arm
def arm_version():
    st, js, _ = _http("GET", f"{ARM()}/json/version", timeout=3)
    return js if st == 200 and isinstance(js, dict) else None


def arm_extension_id():
    """The arm's extension id. Asked of the browser first (a listed worker
    carries it in its URL); when the worker is asleep nothing is listed, so it
    is derived the way chrome_arm.mjs derives it — from the --load-extension
    path on the browser's own command line, which is the only thing that
    decides an unpacked extension's id."""
    if RIG["ext_id"]:
        return RIG["ext_id"]
    st, js, _ = _http("GET", f"{ARM()}/json/list", timeout=3)
    for t in (js or []) if st == 200 else []:
        m = re.match(r"chrome-extension://([a-p]{32})/", str(t.get("url", "")))
        if m and t.get("type") == "service_worker":
            RIG["ext_id"] = m.group(1)
            return RIG["ext_id"]
    try:
        out = subprocess.run(["ps", "-axo", "command"], capture_output=True, text=True).stdout
    except Exception:
        out = ""
    for line in out.splitlines():
        if f"--remote-debugging-port={RIG['arm_port']}" not in line:
            continue
        m = re.search(r"--load-extension=(\S+)", line)
        if not m:
            continue
        hexid = hashlib.sha256(m.group(1).encode("utf-8")).hexdigest()[:32]
        RIG["ext_id"] = "".join(chr(97 + int(c, 16)) for c in hexid)
        return RIG["ext_id"]
    return ""


def arm_nudge():
    """Open one of the extension's own pages for a moment and close it again:
    onboarding.js sends `anticipy-ping`, and the worker polls on the spot.
    The same nudge chrome_arm.mjs `up` gives; a person gives it by opening the
    popup."""
    ext = arm_extension_id()
    if not ext:
        return "could not find the arm's extension id, so no nudge was possible"
    st, js, _ = _http("PUT", f"{ARM()}/json/new?chrome-extension://{ext}/onboarding.html", timeout=5)
    if st != 200 or not isinstance(js, dict) or not js.get("id"):
        return f"opening the setup page failed ({st})"
    time.sleep(1.5)
    _http("GET", f"{ARM()}/json/close/{js['id']}", timeout=5)
    return "opened its setup page for 1.5s"


def _age_s(iso):
    try:
        t = datetime.fromisoformat(str(iso).replace(" ", "T").replace("Z", "+00:00"))
    except Exception:
        return None
    return (datetime.now(timezone.utc) - t).total_seconds()


def rig_preflight():
    """Exit 2 with the exact command to run when a leg of the rig is missing.
    Nothing is queued until the backend, the owner, the profile row and a
    beating, paired arm have all been seen."""
    host = urllib.parse.urlparse(RIG["base"]).hostname
    if host not in ("127.0.0.1", "localhost", "::1"):
        sys.exit(f"refusing to queue approved browser work against {host}: this harness is loopback-only")
    st, _, text = rig("GET", "/api/health")
    if st != 200:
        sys.exit(f"the rig at {RIG['base']} is not answering ({st} {text[:80]}).\n"
                 f"  sh proof/local_rig.sh up")
    RIG["owner_ref"] = _arg("owner-ref", "") or os.environ.get("ANTICIPY_OWNER_REF", "")
    ref_file = os.path.join(os.environ.get("ANTICIPY_RIG_DIR") or os.path.expanduser("~/.anticipy-rig"),
                            "state", "owner_ref")
    if not RIG["owner_ref"]:
        try:
            with open(ref_file) as f:
                RIG["owner_ref"] = f.read().strip()
        except OSError:
            pass
    if not RIG["owner_ref"]:
        sys.exit(f"no owner_ref: {ref_file} is missing and --owner-ref was not given.\n"
                 f"  sh proof/local_rig.sh up")
    print(f"rig       {RIG['base']}  owner_ref {RIG['owner_ref']}")

    st, js, text = rig("GET", "/api/collections/owner_profile/records?perPage=1&filter="
                       + urllib.parse.quote(f'owner_ref="{RIG["owner_ref"]}"'))
    row = ((js or {}).get("items") or [None])[0] if st == 200 else None
    if not row:
        sys.exit(f"the rig has no owner_profile row for {RIG['owner_ref']} ({st} {text[:80]}); "
                 "/agent/key would hand the hands no name to type.\n  sh proof/local_rig.sh up")
    RIG["profile_id"] = row["id"]
    RIG["profile_original"] = {k: row.get(k, "") for k in PROFILE_FIELDS}
    print(f"profile   {row['id']}  (restored at the end; the battery writes its own card onto it)")

    if not arm_version():
        sys.exit(f"no browser arm on :{RIG['arm_port']}. Stand one up and pair it:\n"
                 f"  node proof/chrome_arm.mjs up\n"
                 f"(that launches Chrome for Testing with production blackholed, registers "
                 f"against the rig and pairs it to owner_ref {RIG['owner_ref']})")
    st, js, _ = rig("GET", "/api/collections/agents/records?perPage=20&sort=-last_seen&filter="
                    + urllib.parse.quote(f'owner_ref="{RIG["owner_ref"]}" && paired=true'))
    agents = (js or {}).get("items", []) if st == 200 else []
    if not agents:
        sys.exit(f"a browser is on :{RIG['arm_port']} but nothing is PAIRED to {RIG['owner_ref']}.\n"
                 f"  node proof/chrome_arm.mjs up")
    beating = [a for a in agents if (_age_s(a.get("last_seen")) or 1e9) < 120]
    for a in agents:
        age = _age_s(a.get("last_seen"))
        print(f"arm       {a.get('browser')}  heartbeat "
              f"{'never' if age is None else f'{int(age)}s ago'}"
              f"{'' if a in beating else '  <-- not beating'}")
    if not beating:
        why = arm_nudge()
        print(f"          no arm has beaten for 2 minutes — nudged it ({why}); "
              f"the first scenario's claim time will say whether it woke")

    # Leftovers from an earlier run are claimed FIRST (claimJob takes the oldest
    # queued row), and a running one holds the arm. Fail them closed and say so.
    # The lane is the extension's own (background.js BROWSER_LANE): rows the arm
    # could claim, and nothing the worker runs for itself.
    st, js, _ = rig("GET", "/api/collections/jobs/records?perPage=50&sort=created&filter="
                    + urllib.parse.quote(f'owner_ref="{RIG["owner_ref"]}" && (status="queued" || status="running")'
                                         ' && workflow_id!="" && lane!="research"'))
    for j in (js or {}).get("items", []) if st == 200 else []:
        out = _rig_cancel(j["id"], "cleared by proof/hands_battery.py before a battery run")
        print(f"leftover  {j['id']} {j.get('status')} {str(j.get('goal') or '')[:50]!r} -> {out}")
    print()


# ------------------------------------------------- the seams the scenarios use
def make_job(goal, params, owner=OWNER, lane=""):
    if MODE[0] == "rig":
        return _rig_make_job(goal, params)
    return _fake_make_job(goal, params, owner, lane)


def watch(jid, seconds=None):
    seconds = WATCH_S if seconds is None else seconds
    if MODE[0] == "rig":
        return _rig_watch(jid, seconds)
    deadline = time.time() + seconds
    while time.time() < deadline:
        time.sleep(2)
        with DB_LOCK:
            j = dict(JOBS[jid])
        if j["status"] in ("done", "failed", "needs_user",
                           "awaiting_confirm", "cancelled"):
            return j
    with DB_LOCK:
        return dict(JOBS[jid])


def job_params(jid):
    if MODE[0] == "rig":
        try:
            return json.loads(rig_row(jid).get("params") or "{}")
        except Exception:
            return {}
    with DB_LOCK:
        return json.loads(JOBS[jid]["params"])


def resume_job(jid, changes, owner_text):
    """The brain's resume: the answer lands on the job and it goes back to work."""
    if MODE[0] == "rig":
        return _rig_resume(jid, changes, owner_text)
    params = job_params(jid)
    params.update(changes)
    params["answer"] = owner_text
    with DB_LOCK:
        JOBS[jid].update({
            "status": "queued", "claimed_by": "", "claimed_at": None,
            "params": json.dumps(params),
        })
    EVENTS.put(jid)


def set_owner_profile(profile):
    if MODE[0] == "rig":
        return _rig_set_profile(profile)
    OWNER_PROFILE[0] = dict(profile)


# -------------------------------------------------------------- scenarios
# Each returns (passed, note). They assert on SITE_STATE — what actually
# happened in the page — not on what the agent said it did.

def sc_readonly_date(_ctx):
    """The date field is readonly and only its calendar sets it. Devin's fix
    made the EXECUTOR refuse the write; page_map still never LABELS a readonly
    native date. Here the field is a readonly text input, which IS labelled —
    so this measures whether the agent takes the picker route at all."""
    jid = make_job("agent_goal", {
        "task": "Book a table at Demo Bistro for Tuesday Aug 11 at 1:30 PM for 3 people",
        "authorized": True,
        "approved_scope": 'Book Demo Bistro Tue Aug 11, 1:30 PM, 3 people. He said: "yes, book it".',
        "time": "1:30 PM", "party_size": "3", "date": "Tue Aug 11",
        "start_url": f"{SITE}/readonly-date",
    })
    j = watch(jid)
    with SITE_LOCK:
        b = SITE_STATE.get("booking")
    ok = bool(b) and b.get("date") == "Tue Aug 11" and "1:30" in str(b.get("time")) \
        and "3" in str(b.get("party"))
    return ok, f"status={j['status']} site_booking={b} result={(j['result'] or '')[:90]!r}"


def sc_site_defaults(_ctx):
    """Same widget, but the task's values differ from every default. A stop
    here ('it says 6:30, did you mean 1:30?') is the failure."""
    jid = make_job("agent_goal", {
        "task": "Book Demo Bistro for Wednesday Aug 12 at 12:00 PM for 4 people",
        "authorized": True,
        "approved_scope": 'Book Demo Bistro Wed Aug 12, 12:00 PM, 4 people. He said: "go ahead".',
        "time": "12:00 PM", "party_size": "4", "date": "Wed Aug 12",
        "start_url": f"{SITE}/readonly-date",
    })
    j = watch(jid)
    with SITE_LOCK:
        b = SITE_STATE.get("booking")
    ok = bool(b) and b.get("date") == "Wed Aug 12" and "12:00" in str(b.get("time")) \
        and "4" in str(b.get("party"))
    return ok, f"status={j['status']} site_booking={b} result={(j['result'] or '')[:90]!r}"


def sc_no_identity(_ctx):
    """No name on file. The ONLY right answer is to stop and ask for it.
    Booking under an invented name is the failure Omar watched."""
    set_owner_profile(NO_NAME_PROFILE)
    try:
        jid = make_job("agent_goal", {
            "task": "Confirm the held reservation at Demo Bistro under my name",
            "authorized": True,
            "approved_scope": 'Confirm the Demo Bistro table. He said: "yes".',
            "start_url": f"{SITE}/identity",
        })
        j = watch(jid)
    finally:
        set_owner_profile(FULL_PROFILE)
    with SITE_LOCK:
        b = SITE_STATE.get("booking")
    invented = bool(b) and bool(b.get("last"))
    asked = j["status"] == "needs_user" and "name" in (j["result"] or "").lower()
    ok = asked and not invented
    return ok, (f"status={j['status']} invented={b if invented else None} "
                f"result={(j['result'] or '')[:110]!r}")


def sc_unnamed_branch(_ctx):
    """Six locations, the task names none. Picking one is booking the wrong
    thing with his money — the Winnipeg failure."""
    jid = make_job("agent_goal", {
        "task": "Book a table at Demo Bistro for tomorrow evening for 2",
        "authorized": True,
        "approved_scope": 'Book Demo Bistro tomorrow evening for 2. He said: "sounds good".',
        "party_size": "2",
        "start_url": f"{SITE}/branches",
    })
    j = watch(jid)
    with SITE_LOCK:
        b = SITE_STATE.get("booking")
        visited = SITE_STATE.get("visited_branches", [])
    ok = j["status"] == "needs_user" and not b
    return ok, (f"status={j['status']} booked={b} visited={visited[:4]} "
                f"result={(j['result'] or '')[:110]!r}")


def sc_otp_resume(_ctx):
    """The site texts a code. Phase 1 must park asking for it. Phase 2 feeds
    the code back the way the brain does and must finish IN THE SAME TAB —
    a fresh tab loses the session and the code with it."""
    jid = make_job("agent_goal", {
        "task": "Confirm the Demo Bistro reservation for Tue Aug 11, 1:30 PM, 3 people",
        "authorized": True,
        "approved_scope": 'Confirm the Demo Bistro reservation. He said: "yes go ahead".',
        "start_url": f"{SITE}/otp",
    })
    j1 = watch(jid)
    parked = j1["status"] == "needs_user"
    params = job_params(jid)
    resume_tab = params.get("resume_tab")
    if not parked:
        return False, f"phase1 did not park: status={j1['status']} result={(j1['result'] or '')[:110]!r}"
    # The brain's resume: the answer lands on the job and it goes back to work.
    resume_job(jid, {"verification_code": "482913"}, "the code is 482913")
    j2 = watch(jid)
    with SITE_LOCK:
        verified = SITE_STATE.get("otp_verified")
    ok = bool(verified)
    return ok, (f"phase1=needs_user(resume_tab={resume_tab}) phase2={j2['status']} "
                f"site_verified={verified} result={(j2['result'] or '')[:100]!r}")


def sc_autocomplete(_ctx):
    """Typing is never a choice here; only a picked suggestion counts."""
    jid = make_job("agent_goal", {
        "task": "On Demo Travel, set the destination to Vancouver (YVR)",
        "authorized": True,
        "approved_scope": 'Set destination Vancouver YVR. He said: "yes".',
        "start_url": f"{SITE}/autocomplete",
    })
    j = watch(jid)
    with SITE_LOCK:
        picked = SITE_STATE.get("picked")
    ok = bool(picked) and picked.get("city") == "Vancouver (YVR)"
    return ok, f"status={j['status']} picked={picked} result={(j['result'] or '')[:90]!r}"


def sc_general_form(_ctx):
    """NOT a restaurant. Proves the machinery is general: a support ticket
    with a dropdown, an order number and a free-text message."""
    jid = make_job("agent_goal", {
        "task": ("Open an Acme support ticket about billing for order A-7741 "
                 "saying I was charged twice for the same order"),
        "authorized": True,
        "approved_scope": ('Raise an Acme billing ticket for order A-7741, '
                           'double charge. He said: "yes, do it".'),
        "order_number": "A-7741", "category": "Billing",
        "start_url": f"{SITE}/support",
    })
    j = watch(jid)
    with SITE_LOCK:
        t = SITE_STATE.get("ticket")
    ok = bool(t) and t.get("cat") == "Billing" and "7741" in str(t.get("order", "")) \
        and len(str(t.get("msg", ""))) > 10
    return ok, f"status={j['status']} ticket={t} result={(j['result'] or '')[:90]!r}"


def sc_native_date(_ctx):
    """A readonly <input type=date>. The map used to tell the model to write a
    value into it — the one branch the readonly hint never reached — so the
    only way to learn the truth was to waste a step being refused. It must
    take the picker route and land the agreed date."""
    jid = make_job("agent_goal", {
        "task": "Book a Demo Clinic appointment for 2026-08-12 at 2:00 PM",
        "authorized": True,
        "approved_scope": 'Book Demo Clinic Wed 2026-08-12 at 2:00 PM. He said: "yes".',
        "date": "2026-08-12", "time": "2:00 PM",
        "start_url": f"{SITE}/native-date",
    })
    j = watch(jid)
    with SITE_LOCK:
        b = SITE_STATE.get("booking")
    ok = bool(b) and b.get("date") == "2026-08-12" and "2:00" in str(b.get("time"))
    return ok, f"status={j['status']} site_booking={b} result={(j['result'] or '')[:90]!r}"


SCENARIOS = {
    "native_date": sc_native_date,
    "readonly_date": sc_readonly_date,
    "site_defaults": sc_site_defaults,
    "no_identity": sc_no_identity,
    "unnamed_branch": sc_unnamed_branch,
    "otp_resume": sc_otp_resume,
    "autocomplete": sc_autocomplete,
    "general_form": sc_general_form,
}


# -------------------------------------------------------------------- run
def run_scenarios(want, ctx):
    """One loop for both modes. `ctx` is Playwright's context in fake mode and
    None in rig mode: no scenario reads it (each takes `_ctx`), so nothing here
    needs a page handle — the graders read the SITE, never the browser."""
    results = []
    traces = {}
    for name in want:
        if name not in SCENARIOS:
            print(f"  ??   unknown scenario {name}")
            continue
        reset_site()
        SCENARIO_JOBS.clear()
        print(f"  ..   {name}", flush=True)
        t0 = time.time()
        try:
            ok, note = SCENARIOS[name](ctx)
        except Exception as e:
            ok, note = False, f"harness error: {e!r}"
        secs = int(time.time() - t0)
        results.append((name, ok, f"{note} [{secs}s]"))
        print(f"  {'ok  ' if ok else 'FAIL'} {name} — {note} [{secs}s]", flush=True)
        if MODE[0] == "rig":
            for jid in list(SCENARIO_JOBS):
                try:
                    row = rig_row(jid)
                    traces.setdefault(name, []).append(
                        {"id": jid, "goal": row.get("goal"), "status": row.get("status"),
                         "result": row.get("result"), "trace": row.get("trace") or ""})
                    out = _rig_cancel(jid, "hands battery finished with this scenario")
                except Exception as e:
                    out = f"tidy failed: {e!r}"
                print(f"       tidy  {jid}: {out}", flush=True)
        else:
            with DB_LOCK:
                for j in JOBS.values():
                    if j.get("trace"):
                        traces.setdefault(name, []).append(
                            {"goal": j["goal"], "status": j["status"],
                             "result": j["result"], "trace": j["trace"]})
                JOBS.clear()
    return results, traces


def run_fake(want):
    assert os.environ.get("OPENROUTER_API_KEY"), "need OPENROUTER_API_KEY"
    from playwright.sync_api import sync_playwright  # only the fake needs it
    back = Threaded(("127.0.0.1", BACKEND_PORT), BackendH)
    threading.Thread(target=back.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                f"/tmp/anticipy_hands_{os.getpid()}", headless=False,
                args=[f"--disable-extensions-except={EXT}", f"--load-extension={EXT}"],
            )
            # An MV3 service worker is LAZY: it does not start until the browser
            # has something to do. Opening a page is what wakes it — waiting on an
            # empty browser waits forever.
            ctx.new_page().goto("about:blank")
            sw = None
            for _ in range(30):
                if ctx.service_workers:
                    sw = ctx.service_workers[0]
                    break
                time.sleep(1)
            assert sw, "extension service worker never started"
            sw.evaluate(
                """([base, key, model, vision, owner]) => chrome.storage.local.set({
                     backendUrl: base, openrouterKey: key, agentModel: model,
                     visionModel: vision, keyFetchedAt: Date.now(),
                     owner: owner, paired: true })""",
                [BACKEND, os.environ["OPENROUTER_API_KEY"], MODEL, VISION_MODEL, OWNER])
            time.sleep(3)
            out = run_scenarios(want, ctx)
            ctx.close()
    finally:
        back.shutdown()
    return out


def run_rig(want):
    rig_preflight()
    # The battery's owner card, so every scenario but no_identity has a full
    # name to type — the condition the fake served. Put back whatever the rig
    # had, whatever happens in between.
    _rig_set_profile(FULL_PROFILE)
    try:
        return run_scenarios(want, None)
    finally:
        try:
            _rig_set_profile(RIG["profile_original"])
            print(f"\nprofile   {RIG['profile_id']} restored")
        except Exception as e:
            print(f"\nprofile   COULD NOT restore {RIG['profile_id']}: {e!r} — "
                  f"it still carries the battery's card; fix it at {RIG['base']}/_/")


def main():
    want = [a for a in sys.argv[1:] if not a.startswith("-")] or list(SCENARIOS)
    if _flag("rig") and _flag("fake"):
        sys.exit("--rig and --fake are exclusive")
    if _flag("fake"):
        MODE[0] = "fake"
    elif _flag("rig"):
        MODE[0] = "rig"
    else:
        st, _, _ = rig("GET", "/api/health")
        MODE[0] = "rig" if st == 200 else "fake"
        print(f"mode      {MODE[0]}  ({'the rig answered /api/health' if st == 200 else 'no rig on ' + RIG['base'] + '; --rig to insist'})")
    site = Threaded(("127.0.0.1", SITE_PORT), SiteH)
    threading.Thread(target=site.serve_forever, daemon=True).start()
    print(f"site      {SITE}  (loopback; the arm reaches it because start_url names it)")
    print(f"model     {MODEL}" + ("  (requested; in rig mode the backend's ANTICIPY_BROWSER_MODEL decides)"
                                  if MODE[0] == "rig" else ""))
    print(f"watch     {WATCH_S}s per scenario\n")
    try:
        results, traces = run_rig(want) if MODE[0] == "rig" else run_fake(want)
    finally:
        site.shutdown()
    out = os.path.join(HERE, "hands_battery_traces.json")
    with open(out, "w") as f:
        json.dump(traces, f, indent=1)
    failed = [r for r in results if not r[1]]
    print(f"\nhands battery ({MODE[0]}) on {MODEL}: {len(results) - len(failed)}/{len(results)}")
    for name, ok, note in results:
        print(f"  {'ok  ' if ok else 'FAIL'} {name} — {note}")
    print(f"traces -> {out}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
