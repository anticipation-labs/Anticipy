#!/usr/bin/env python3
"""Twenty day-zero capabilities through the packaged Chrome extension.

This is deliberately not the old permissive fake-backend battery. It uses:
  * a disposable PocketBase with the production migrations and hooks,
  * a fresh signed-in owner and a server-issued per-agent credential,
  * canonical approved workflows with leases and verified receipts,
  * the packaged MV3 extension in an isolated Chromium profile, and
  * server-side site state as the oracle (never the agent's own claim).

The sites are deterministic local stand-ins for generic web forms. The cases
vary labels, controls, defaults and domains; there are no per-site recipes in
the extension. OPENROUTER_API_KEY is the only external dependency.
"""
from __future__ import annotations

import html
import http.server
import json
import os
from pathlib import Path
import socketserver
import sys
import tempfile
import threading
import time
import urllib.parse
import uuid

import requests
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "extension"
PB = os.getenv("PB_BASE", "http://127.0.0.1:18091").rstrip("/")
SERVICE_TOKEN = os.getenv("RIG_SERVICE_TOKEN", "rig-worker-secret")
SITE_PORT = int(os.getenv("ANTICIPY_SCENARIO_PORT", "18792"))
SITE = f"http://127.0.0.1:{SITE_PORT}"
MODEL = os.getenv("ANTICIPY_MODEL", "google/gemini-2.5-flash")
VISION_MODEL = os.getenv("ANTICIPY_VISION_MODEL", MODEL)

sys.path.insert(0, str(ROOT))
from brain.workflow import Consequence, approve, new_plan, put_in_params  # noqa: E402


def field(name, label, value, kind="text", options=(), required=True):
    return {"name": name, "label": label, "value": value, "kind": kind,
            "options": list(options), "required": required}


CASES = [
    {"slug": "sink", "title": "Harbour Homes — Maintenance",
     "task": "Submit a maintenance request for unit 18B: the kitchen sink is leaking under the cabinet, mark it urgent, and allow entry if nobody is home.",
     "fields": [field("unit", "Apartment or unit", "18B"),
                field("category", "What needs attention?", "Plumbing", "select", ["Choose one", "Heating", "Plumbing", "Electrical"]),
                field("details", "Describe the problem", "Kitchen sink is leaking under the cabinet", "textarea"),
                field("priority", "How urgent is it?", "Urgent", "select", ["Routine", "Soon", "Urgent"]),
                field("entry", "Management may enter if nobody is home", True, "checkbox")]},
    {"slug": "utility", "title": "NorthGrid — Bill review",
     "task": "Dispute the July 2026 electricity bill on account UT-20491: it is $318.44 versus the usual $104.12. Ask NorthGrid to review and correct the bill.",
     "fields": [field("account", "Account number", "UT-20491"),
                field("period", "Billing period", "July 2026"),
                field("charged", "Amount charged", "318.44"),
                field("usual", "Usual amount", "104.12"),
                field("resolution", "What should we do?", "Review and correct the bill", "select", ["Explain the bill", "Review and correct the bill", "Payment plan"])]},
    {"slug": "delivery", "title": "ParcelMarket — Replace an item",
     "task": "Request a replacement for the ceramic table lamp in order PK-77104 because it arrived cracked. Do not request a refund.",
     "fields": [field("order", "Order number", "PK-77104"),
                field("item", "Item", "Ceramic table lamp"),
                field("problem", "What happened?", "Arrived cracked", "select", ["Wrong item", "Arrived cracked", "Missing parts"]),
                field("resolution", "Preferred resolution", "Replacement", "select", ["Refund", "Replacement", "Store credit"])]},
    {"slug": "laptop", "title": "Northstar Computers — Warranty service",
     "task": "Open a mail-in warranty repair for laptop serial MBP-X9-4421 because the display flickers after waking from sleep.",
     "fields": [field("serial", "Device serial number", "MBP-X9-4421"),
                field("issue", "Tell us what is wrong", "Display flickers after waking from sleep", "textarea"),
                field("service", "Service preference", "Mail-in repair", "select", ["Choose", "Mail-in repair", "Store appointment"])]},
    {"slug": "vehicle", "title": "Roadline — Recall appointment",
     "task": "Schedule recall R24-118 for VIN 1HGBH41JXMN109186 at North Shore Auto on August 18, 2026 at 2:00 PM.",
     "fields": [field("vin", "17-character VIN", "1HGBH41JXMN109186"),
                field("recall", "Recall campaign", "R24-118"),
                field("dealer", "Preferred dealer", "North Shore Auto", "select", ["Choose dealer", "Downtown Motors", "North Shore Auto"]),
                field("date", "Appointment date", "2026-08-18", "date"),
                field("time", "Appointment time", "2:00 PM", "select", ["9:00 AM", "11:30 AM", "2:00 PM"])]},
    {"slug": "passport", "title": "Travel Documents — Renewal intake",
     "task": "Submit the passport renewal intake for Omar Ebrahim, born June 14, 1990, with travel planned for November 20, 2026. Use standard service.",
     "fields": [field("service", "Application type", "Renewal", "select", ["New passport", "Renewal", "Replacement"]),
                field("name", "Full legal name", "Omar Ebrahim"),
                field("birth", "Date of birth", "1990-06-14", "date"),
                field("travel", "Planned travel date", "2026-11-20", "date"),
                field("speed", "Processing speed", "Standard", "select", ["Standard", "Urgent"])]},
    {"slug": "license", "title": "Professional Registry — Renewal",
     "task": "Renew professional license ARCH-48217, expiring September 30, 2026, and confirm that the required continuing education is complete.",
     "fields": [field("license", "License number", "ARCH-48217"),
                field("expiry", "Current expiry date", "2026-09-30", "date"),
                field("education", "Required continuing education is complete", True, "checkbox"),
                field("term", "Renewal term", "1 year", "select", ["1 year", "2 years"])]},
    {"slug": "invoice", "title": "Vendor Portal — Invoice discrepancy",
     "task": "Dispute vendor invoice INV-8842 against purchase order PO-1907: billed $12,840.00, agreed $11,840.00. Request a corrected invoice.",
     "fields": [field("invoice", "Invoice number", "INV-8842"),
                field("po", "Purchase order", "PO-1907"),
                field("billed", "Billed total", "12840.00"),
                field("agreed", "Agreed total", "11840.00"),
                field("request", "Resolution requested", "Corrected invoice", "select", ["Explanation", "Credit note", "Corrected invoice"])]},
    {"slug": "saas", "title": "CloudDesk — Subscription seats",
     "task": "Reduce the Anticipy workspace from 24 CloudDesk seats to 17, effective at renewal, and keep the Pro plan.",
     "fields": [field("workspace", "Workspace", "Anticipy"),
                field("plan", "Plan", "Pro", "select", ["Starter", "Pro", "Enterprise"]),
                field("seats", "Number of seats", "17", "number"),
                field("effective", "When should this change?", "At renewal", "select", ["Immediately", "At renewal"])]},
    {"slug": "renewal", "title": "Account Hub — Recovery brief",
     "task": "Create a renewal recovery brief for Northwind Foods: renewal is October 15, 2026, risk is low adoption, and the next step is an executive training session.",
     "fields": [field("customer", "Customer", "Northwind Foods"),
                field("renewal", "Renewal date", "2026-10-15", "date"),
                field("risk", "Primary risk", "Low adoption", "select", ["Budget", "Low adoption", "Competitor"]),
                field("next", "Recommended next step", "Executive training session", "textarea")],
     "submit": "Create recovery brief"},
    {"slug": "conference", "title": "Future Systems — Speaker portal",
     "task": "Submit a conference talk titled 'Agents That Earn Trust' to the Applied AI track as a 30-minute talk. Abstract: Durable state, evidence, and safe recovery for assistants that act.",
     "fields": [field("title", "Session title", "Agents That Earn Trust"),
                field("track", "Conference track", "Applied AI", "select", ["Product", "Applied AI", "Security"]),
                field("format", "Session format", "30-minute talk", "select", ["Lightning talk", "30-minute talk", "Workshop"]),
                field("abstract", "Abstract", "Durable state, evidence, and safe recovery for assistants that act.", "textarea")]},
    {"slug": "grant", "title": "Civic Spark — Grant application",
     "task": "Submit a $25,000 pilot grant application for Anticipy Labs to the Accessible Technology Pilot program. Summary: A privacy-first assistant that helps people complete everyday digital paperwork.",
     "fields": [field("organization", "Applicant organization", "Anticipy Labs"),
                field("program", "Funding program", "Accessible Technology Pilot", "select", ["Community Arts", "Accessible Technology Pilot", "Climate Action"]),
                field("amount", "Amount requested", "25000", "number"),
                field("summary", "Project summary", "A privacy-first assistant that helps people complete everyday digital paperwork.", "textarea")]},
    {"slug": "guest", "title": "Harbour Tower — Guest parking",
     "task": "Register Jordan Lee's vehicle BC plate K8M 2P4 for guest parking at unit 1802 on August 16, 2026 from 6:00 PM to 11:00 PM.",
     "fields": [field("unit", "Resident unit", "1802"),
                field("guest", "Guest name", "Jordan Lee"),
                field("plate", "License plate", "K8M 2P4"),
                field("date", "Visit date", "2026-08-16", "date"),
                field("window", "Parking window", "6:00 PM to 11:00 PM") ]},
    {"slug": "fieldtrip", "title": "Cedar School — Permission form",
     "task": "Give permission for Maya Ebrahim to attend the Science World field trip on September 4, 2026. Emergency contact is Omar Ebrahim at +1 604 555 0142.",
     "fields": [field("student", "Student name", "Maya Ebrahim"),
                field("trip", "Trip", "Science World", "select", ["Museum of Anthropology", "Science World", "Aquarium"]),
                field("date", "Trip date", "2026-09-04", "date"),
                field("contact", "Emergency contact", "Omar Ebrahim — +1 604 555 0142"),
                field("consent", "I give permission for this trip", True, "checkbox")]},
    {"slug": "pet", "title": "Companion Vet — Vaccination",
     "task": "Book Luna, a dog, for a rabies vaccination at Companion Vet on August 20, 2026 at 10:30 AM.",
     "fields": [field("pet", "Pet name", "Luna"),
                field("species", "Animal", "Dog", "select", ["Cat", "Dog", "Other"]),
                field("service", "Visit reason", "Rabies vaccination", "select", ["Annual exam", "Rabies vaccination", "Dental"]),
                field("date", "Date", "2026-08-20", "date"),
                field("time", "Time", "10:30 AM", "select", ["9:00 AM", "10:30 AM", "3:00 PM"])]},
    {"slug": "appliance", "title": "HomeWorks — Recall remedy",
     "task": "Request a replacement for recalled HomeWorks kettle model HWK-220, serial KTL-771902, shipped to 1550 Marine Drive, West Vancouver BC V7V 1H8.",
     "fields": [field("model", "Model number", "HWK-220"),
                field("serial", "Serial number", "KTL-771902"),
                field("remedy", "Preferred remedy", "Replacement", "select", ["Repair", "Replacement", "Refund"]),
                field("address", "Shipping address", "1550 Marine Drive, West Vancouver BC V7V 1H8", "textarea")]},
    {"slug": "windshield", "title": "Coast Insurance — Glass claim",
     "task": "Open a windshield claim on policy AUTO-441208 for damage on August 11, 2026 in West Vancouver: a highway stone caused a 20 cm crack. Choose North Shore Glass for repair.",
     "fields": [field("policy", "Policy number", "AUTO-441208"),
                field("date", "Date of damage", "2026-08-11", "date"),
                field("location", "Where did it happen?", "West Vancouver"),
                field("damage", "Describe the damage", "Highway stone caused a 20 cm crack", "textarea"),
                field("shop", "Repair facility", "North Shore Glass", "select", ["Choose a shop", "Downtown Auto Glass", "North Shore Glass"])]},
    {"slug": "expense", "title": "Ledgerly — New expense",
     "task": "Submit a $86.40 client-meal expense from Cedar & Salt dated August 10, 2026, category Meals, purpose 'Investor product review'.",
     "fields": [field("merchant", "Merchant", "Cedar & Salt"),
                field("date", "Purchase date", "2026-08-10", "date"),
                field("amount", "Amount", "86.40"),
                field("category", "Expense category", "Meals", "select", ["Travel", "Meals", "Software"]),
                field("purpose", "Business purpose", "Investor product review", "textarea")]},
    {"slug": "accessibility", "title": "Event Access — Accommodation",
     "task": "Request front-row seating and live captions for Omar Ebrahim at Demo Day on September 12, 2026. Contact omar@example.com.",
     "fields": [field("attendee", "Attendee name", "Omar Ebrahim"),
                field("event", "Event", "Demo Day"),
                field("date", "Event date", "2026-09-12", "date"),
                field("request", "Accommodation requested", "Front-row seating and live captions", "textarea"),
                field("email", "Contact email", "omar@example.com", "email")]},
    {"slug": "moving", "title": "MoveTogether — Utility transfer",
     "task": "Schedule electricity and water to move on September 1, 2026 from 88 Seaside Ave to 1550 Marine Drive. Keep service at the old address through August 31.",
     "fields": [field("old", "Current service address", "88 Seaside Ave", "textarea"),
                field("new", "New service address", "1550 Marine Drive", "textarea"),
                field("services", "Services to move", "Electricity and water", "select", ["Electricity only", "Water only", "Electricity and water"]),
                field("start", "Start at new address", "2026-09-01", "date"),
                field("end", "Last day at old address", "2026-08-31", "date")]},
]

CASES_BY_SLUG = {c["slug"]: c for c in CASES}
SITE_STATE = {}
SITE_LOCK = threading.Lock()


def render_control(spec):
    name = html.escape(spec["name"])
    label = html.escape(spec["label"])
    required = " required" if spec["required"] and spec["kind"] != "checkbox" else ""
    kind = spec["kind"]
    if kind == "select":
        options = "".join(f'<option value="{html.escape(str(x))}">{html.escape(str(x))}</option>'
                          for x in spec["options"])
        control = f'<select id="{name}" name="{name}"{required}>{options}</select>'
    elif kind == "textarea":
        control = f'<textarea id="{name}" name="{name}" rows="3"{required}></textarea>'
    elif kind == "checkbox":
        control = f'<input id="{name}" name="{name}" type="checkbox">'
    else:
        control = f'<input id="{name}" name="{name}" type="{html.escape(kind)}"{required}>'
    return f'<label for="{name}"><span>{label}</span>{control}</label>'


def render_case(case):
    controls = "".join(render_control(f) for f in case["fields"])
    submit = html.escape(case.get("submit", "Review and submit"))
    slug = html.escape(case["slug"])
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>{html.escape(case['title'])}</title><style>
body{{font:16px system-ui;margin:36px auto;max-width:720px;color:#17202a}}
main{{border:1px solid #ccd3da;border-radius:16px;padding:26px;box-shadow:0 8px 35px #ccd3da66}}
label{{display:grid;gap:6px;margin:16px 0}} input,select,textarea{{font:inherit;padding:10px;border:1px solid #8794a1;border-radius:8px}}
input[type=checkbox]{{width:22px;height:22px}} button{{font:600 16px system-ui;padding:12px 18px;border:0;border-radius:10px;background:#153a63;color:white}}
#receipt{{margin-top:20px;padding:16px;background:#e8f6ec;border-radius:10px;font-weight:650}}
</style></head><body><main><p>Secure customer portal</p><h1>{html.escape(case['title'])}</h1>
<form id="request">{controls}<button id="submit" type="submit">{submit}</button></form>
<div id="receipt" role="status" hidden></div></main><script>
request.addEventListener('submit', async (event) => {{
 event.preventDefault(); const payload = {{}};
 for (const el of request.elements) {{ if (!el.name) continue; payload[el.name] = el.type === 'checkbox' ? el.checked : el.value; }}
 const response = await fetch('/complete/{slug}', {{method:'POST', headers:{{'Content-Type':'application/json'}}, body:JSON.stringify(payload)}});
 const result = await response.json(); request.hidden = true; receipt.hidden = false;
 const evidence = Object.entries(payload).map(([key, value]) => key + ': ' + String(value)).join(' · ');
 receipt.textContent = result.ok ? 'Submitted successfully. Confirmation #' + result.reference + '. ' + evidence : 'Please correct the highlighted fields.';
}});
</script></body></html>"""


class SiteHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def send_body(self, value, code=200, content_type="text/html"):
        raw = value.encode() if isinstance(value, str) else value
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path.startswith("/case/") and path.split("/")[-1] in CASES_BY_SLUG:
            return self.send_body(render_case(CASES_BY_SLUG[path.split("/")[-1]]))
        return self.send_body("not found", 404, "text/plain")

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        slug = path.split("/")[-1]
        if not path.startswith("/complete/") or slug not in CASES_BY_SLUG:
            return self.send_body("not found", 404, "text/plain")
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length).decode() or "{}")
        except Exception:
            payload = {}
        with SITE_LOCK:
            SITE_STATE[slug] = payload
        return self.send_body(json.dumps({"ok": True, "reference": slug.upper() + "-2026"}),
                              content_type="application/json")

    def log_message(self, *_):
        pass


class ThreadedServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def expect(response, status, label):
    if response.status_code != status:
        raise RuntimeError(f"{label}: {response.status_code} {response.text[:400]}")
    return response


def provision_owner_and_agent():
    suffix = uuid.uuid4().hex[:12]
    email = f"dayzero-{suffix}@example.com"
    password = "Day-zero-proof-password-42!"
    legacy = f"dayzero-{suffix}"
    expect(requests.post(f"{PB}/api/collections/owners/records", json={
        "email": email, "password": password, "passwordConfirm": password,
        "legacy_uuid": legacy, "phone": "+1555" + str(int(suffix[:8], 16))[-7:],
    }, timeout=10), 200, "owner signup")
    auth = expect(requests.post(f"{PB}/api/collections/owners/auth-with-password", json={
        "identity": email, "password": password,
    }, timeout=10), 200, "owner login").json()
    owner_ref, auth_token = auth["record"]["id"], auth["token"]
    headers = {"Authorization": auth_token, "Content-Type": "application/json"}
    expect(requests.post(f"{PB}/api/collections/owner_profile/records", headers=headers, json={
        "owner_ref": owner_ref, "owner_id": legacy, "first_name": "Omar",
        "last_name": "Ebrahim", "email": "omar@example.com",
        "phone": "+16045550142", "facts": "{}",
    }, timeout=10), 200, "profile")
    agent_id = "dayzero-agent-" + uuid.uuid4().hex
    agent = expect(requests.post(f"{PB}/agent/register", json={
        "agent_id": agent_id, "browser": "Day-zero isolated Chromium",
    }, timeout=10), 200, "agent registration").json()
    expect(requests.patch(f"{PB}/api/collections/agents/records/{agent['id']}",
                          headers=headers, json={"owner": legacy,
                                                "owner_ref": owner_ref,
                                                "paired": True}, timeout=10),
           200, "agent pairing")
    return {"owner_ref": owner_ref, "legacy": legacy, "auth": auth_token,
            "agent_id": agent_id, "agent_token": agent["agent_token"],
            "record_id": agent["id"]}


def queue_case(case, identity):
    facts = {f["name"]: f["value"] for f in case["fields"]}
    plan = new_plan(owner_ref=identity["owner_ref"],
                    lineage_key=f"day-zero:{case['slug']}:{uuid.uuid4()}",
                    goal=case["task"], consequence=Consequence.CONSEQUENTIAL,
                    source_event_id=f"scenario:{case['slug']}", facts=facts)
    plan = approve(plan, expected_version=plan.version,
                   owner_words=f"Run the {case['slug']} day-zero proof")
    params = {"task": case["task"], "start_url": f"{SITE}/case/{case['slug']}",
              "authorized": True, "approved_scope": case["task"], **facts}
    params = put_in_params(params, plan)
    body = {**plan.job_fields(), "owner_ref": identity["owner_ref"],
            "owner": identity["legacy"], "goal": plan.goal,
            "lane": "browser", "device_id": "day-zero-proof",
            "params": json.dumps(params, ensure_ascii=False, sort_keys=True)}
    return expect(requests.post(f"{PB}/api/collections/jobs/records",
                                headers={"X-Anticipy-Token": SERVICE_TOKEN,
                                         "Content-Type": "application/json"},
                                json=body, timeout=10), 200,
                  f"queue {case['slug']}").json()


def wait_for_job(job_id, timeout=240):
    deadline = time.time() + timeout
    headers = {"X-Anticipy-Token": SERVICE_TOKEN}
    while time.time() < deadline:
        row = requests.get(f"{PB}/api/collections/jobs/records/{job_id}",
                           headers=headers, timeout=10).json()
        if row.get("status") in {"done", "failed", "needs_user", "cancelled"}:
            return row
        time.sleep(1)
    return requests.get(f"{PB}/api/collections/jobs/records/{job_id}",
                        headers=headers, timeout=10).json()


def values_match(case, actual):
    differences = []
    for spec in case["fields"]:
        expected = spec["value"]
        got = actual.get(spec["name"])
        if isinstance(expected, bool):
            matches = got is expected
        else:
            matches = str(got or "").strip().casefold() == str(expected).strip().casefold()
        if not matches:
            differences.append(f"{spec['name']}={got!r} expected {expected!r}")
    return differences


def main():
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise SystemExit("OPENROUTER_API_KEY is required")
    wanted = [x for x in sys.argv[1:] if x in CASES_BY_SLUG]
    cases = [CASES_BY_SLUG[x] for x in wanted] if wanted else CASES
    expect(requests.get(f"{PB}/api/health", timeout=5), 200, "backend health")
    identity = provision_owner_and_agent()
    server = ThreadedServer(("127.0.0.1", SITE_PORT), SiteHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    results = []
    profile_dir = tempfile.mkdtemp(prefix="anticipy-day-zero-")
    try:
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                profile_dir, headless=False,
                args=[f"--disable-extensions-except={EXTENSION}",
                      f"--load-extension={EXTENSION}"],
            )
            context.new_page().goto("about:blank")
            worker = None
            for _ in range(30):
                if context.service_workers:
                    worker = context.service_workers[0]
                    break
                time.sleep(1)
            if worker is None:
                raise RuntimeError("extension service worker did not start")
            # onInstalled starts its own registration asynchronously. Let it
            # finish before replacing that bootstrap identity with the paired
            # rig identity, or its late response can clobber our setup.
            time.sleep(2)
            worker.evaluate("""(cfg) => chrome.storage.local.set(cfg)""", {
                "backendUrl": PB, "openrouterKey": api_key,
                "agentModel": MODEL, "visionModel": VISION_MODEL,
                "serviceToken": "", "keyFetchedAt": int(time.time() * 1000),
                "owner": identity["legacy"], "ownerRef": identity["owner_ref"],
                "paired": True, "agentId": identity["agent_id"],
                "agentToken": identity["agent_token"],
                "recordId": identity["record_id"],
                "agentCredentialInstalled": True,
                "ownerProfile": {"first_name": "Omar", "last_name": "Ebrahim",
                                 "email": "omar@example.com", "phone": "+16045550142",
                                 "facts": "{}"},
            })
            stored = worker.evaluate("""() => chrome.storage.local.get([
                'agentId','agentToken','recordId','ownerRef','paired','backendUrl'
            ])""")
            expected = {"agentId": identity["agent_id"],
                        "agentToken": identity["agent_token"],
                        "recordId": identity["record_id"],
                        "ownerRef": identity["owner_ref"],
                        "paired": True, "backendUrl": PB}
            if any(stored.get(k) != value for k, value in expected.items()):
                raise RuntimeError("extension identity did not remain pinned to the rig owner")
            # Do not wait for Chrome's alarm floor; begin the first canonical
            # poll only after the identity assertion above has passed.
            worker.evaluate("""() => chrome.alarms.create(
                'anticipy-poll', {when: Date.now() + 100})""")
            time.sleep(1)
            for index, case in enumerate(cases, 1):
                with SITE_LOCK:
                    SITE_STATE.pop(case["slug"], None)
                job = queue_case(case, identity)
                worker.evaluate("""() => chrome.alarms.create(
                    'anticipy-poll', {when: Date.now() + 100})""")
                started = time.time()
                row = wait_for_job(job["id"])
                with SITE_LOCK:
                    actual = dict(SITE_STATE.get(case["slug"], {}))
                differences = values_match(case, actual)
                receipt = {}
                try:
                    receipt = json.loads(row.get("receipt") or "{}")
                except Exception:
                    pass
                ok = (row.get("status") == "done" and not differences
                      and receipt.get("verified") is True
                      and bool(receipt.get("evidence")))
                note = ("stored exact form + verified receipt" if ok else
                        f"status={row.get('status')} differences={differences} "
                        f"result={(row.get('result') or '')[:180]!r}")
                results.append({"scenario": case["slug"], "ok": ok,
                                "seconds": round(time.time() - started, 1),
                                "note": note, "job_id": job["id"]})
                print(f"{'PASS' if ok else 'FAIL'} {index:02d}/{len(cases):02d} {case['slug']}: {note}",
                      flush=True)
                # Keep this isolated browser tidy between scenarios.
                for page in list(context.pages):
                    if page.url.startswith(SITE):
                        try:
                            page.close()
                        except Exception:
                            pass
            context.close()
    finally:
        server.shutdown()
        server.server_close()

    output = ROOT / "work" / "day-zero-20-results.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps({"model": MODEL, "results": results}, indent=2))
    passed = sum(1 for r in results if r["ok"])
    print(f"\nDAY-ZERO 20: {passed}/{len(results)} passed; evidence: {output}")
    raise SystemExit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
