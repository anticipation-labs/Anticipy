"""THE HANDS, WATCHED. The real extension, in a real Chromium, on the real
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

Run:  OPENROUTER_API_KEY=... python3 proof/hands_battery.py [name ...]
"""
from __future__ import annotations

import http.server
import json
import os
import queue
import socketserver
import sys
import threading
import time
import urllib.parse

from playwright.sync_api import sync_playwright

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


# --------------------------------------------------------------- backend
# A faithful-enough stand-in for the production PocketBase: exactly the
# endpoints extension/background.js calls, with the same shapes.
JOBS = {}
AGENTS = {}
DB_LOCK = threading.Lock()
JOB_SEQ = [0]
EVENTS = queue.Queue()


def make_job(goal, params, owner=OWNER, lane=""):
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
# invented-identity test needs a profile with NO name on it.
OWNER_PROFILE = [{
    "first_name": "Omar", "last_name": "Ebrahim",
    "email": "omar@anticipy.ai", "phone": "+16047245161", "facts": "{}",
}]
NO_NAME_PROFILE = {
    "first_name": "", "last_name": "",
    "email": "omar@anticipy.ai", "phone": "+16047245161", "facts": "{}",
}


def watch(jid, seconds=300):
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
    OWNER_PROFILE[0] = dict(NO_NAME_PROFILE)
    try:
        jid = make_job("agent_goal", {
            "task": "Confirm the held reservation at Demo Bistro under my name",
            "authorized": True,
            "approved_scope": 'Confirm the Demo Bistro table. He said: "yes".',
            "start_url": f"{SITE}/identity",
        })
        j = watch(jid)
    finally:
        OWNER_PROFILE[0] = {
            "first_name": "Omar", "last_name": "Ebrahim",
            "email": "omar@anticipy.ai", "phone": "+16047245161", "facts": "{}"}
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
    with DB_LOCK:
        params = json.loads(JOBS[jid]["params"])
    resume_tab = params.get("resume_tab")
    if not parked:
        return False, f"phase1 did not park: status={j1['status']} result={(j1['result'] or '')[:110]!r}"
    # The brain's resume: the answer lands on the job and it goes back to work.
    params["verification_code"] = "482913"
    params["answer"] = "the code is 482913"
    with DB_LOCK:
        JOBS[jid].update({
            "status": "queued", "claimed_by": "", "claimed_at": None,
            "params": json.dumps(params),
        })
    EVENTS.put(jid)
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


def main():
    assert os.environ.get("OPENROUTER_API_KEY"), "need OPENROUTER_API_KEY"
    want = [a for a in sys.argv[1:] if not a.startswith("-")] or list(SCENARIOS)
    site = Threaded(("127.0.0.1", SITE_PORT), SiteH)
    back = Threaded(("127.0.0.1", BACKEND_PORT), BackendH)
    threading.Thread(target=site.serve_forever, daemon=True).start()
    threading.Thread(target=back.serve_forever, daemon=True).start()

    results = []
    traces = {}
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

        for name in want:
            if name not in SCENARIOS:
                print(f"  ??   unknown scenario {name}")
                continue
            reset_site()
            print(f"  ..   {name}", flush=True)
            t0 = time.time()
            try:
                ok, note = SCENARIOS[name](ctx)
            except Exception as e:
                ok, note = False, f"harness error: {e!r}"
            secs = int(time.time() - t0)
            results.append((name, ok, f"{note} [{secs}s]"))
            print(f"  {'ok  ' if ok else 'FAIL'} {name} — {note} [{secs}s]", flush=True)
            with DB_LOCK:
                for j in JOBS.values():
                    if j.get("trace"):
                        traces.setdefault(name, []).append(
                            {"goal": j["goal"], "status": j["status"],
                             "result": j["result"], "trace": j["trace"]})
                JOBS.clear()
        ctx.close()

    site.shutdown()
    back.shutdown()
    out = os.path.join(HERE, "hands_battery_traces.json")
    with open(out, "w") as f:
        json.dump(traces, f, indent=1)
    failed = [r for r in results if not r[1]]
    print(f"\nhands battery on {MODEL}: {len(results) - len(failed)}/{len(results)}")
    print(f"traces -> {out}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
