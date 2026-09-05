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
the extension. Model calls use the same paired-agent backend proxy as a real
customer; the vendor key never enters the disposable Chrome profile.
"""
from __future__ import annotations

import html
import http.server
import json
import os
from pathlib import Path
import random
import re
import shutil
import socketserver
import sys
import tempfile
import threading
import time
import urllib.parse
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

import requests
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "extension"
PB = os.getenv("PB_BASE", "http://127.0.0.1:18091").rstrip("/")
SERVICE_TOKEN = os.getenv("RIG_SERVICE_TOKEN", "rig-worker-secret")
SITE_PORT = int(os.getenv("ANTICIPY_SCENARIO_PORT", "18792"))
SITE = f"http://127.0.0.1:{SITE_PORT}"


def browser_executable() -> str | None:
    """Use an explicit compatible binary, otherwise Playwright's Chromium.

    Playwright's Python package can survive longer than its cached Chromium;
    an explicit override makes that diagnosable. Stable Chrome no longer
    honors automation's side-load-extension flag, so it is not a fallback:
    certification requires the matching Playwright Chromium. The profile is
    disposable and never touches the owner's normal signed-in Chrome state.
    """
    configured = os.getenv("ANTICIPY_BROWSER_EXECUTABLE", "").strip()
    return configured if configured and Path(configured).is_file() else None

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
                field("contact_name", "Emergency contact name", "Omar Ebrahim"),
                field("contact_phone", "Emergency contact phone", "+1 604 555 0142", "tel"),
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


def render_control(spec, mutations=(), ordinal=0):
    name = html.escape(spec["name"])
    label = html.escape(spec["label"])
    required = " required" if spec.get("required", True) and spec["kind"] != "checkbox" else ""
    kind = spec["kind"]
    hostile = "hostile_defaults" in mutations
    expected = spec.get("value")
    wrong = ""
    if hostile:
        wrong = "999" if kind == "number" else f"OLD-{ordinal + 1}"
    if kind == "select":
        choices = list(spec.get("options") or [])
        if not choices:
            choices = ["Choose one", str(expected or "")]
        selected = choices[0] if hostile else None
        options = "".join(
            f'<option value="{html.escape(str(x))}"'
            f'{" selected" if x == selected else ""}>{html.escape(str(x))}</option>'
            for x in choices)
        control = f'<select id="{name}" name="{name}"{required}>{options}</select>'
    elif kind == "textarea":
        control = (f'<textarea id="{name}" name="{name}" rows="3"{required}>'
                   f'{html.escape(wrong)}</textarea>')
    elif kind == "checkbox":
        checked = " checked" if hostile and not bool(expected) else ""
        control = f'<input id="{name}" name="{name}" type="checkbox"{checked}>'
    else:
        list_attr = f' list="suggest-{name}"' if "autocomplete" in mutations and kind == "text" else ""
        control = (f'<input id="{name}" name="{name}" type="{html.escape(kind)}"'
                   f'{required}{list_attr} value="{html.escape(wrong)}">')
        if list_attr:
            control += (f'<datalist id="suggest-{name}"><option value="Previous value">'
                        f'<option value="Not applicable"></datalist>')
    return f'<label for="{name}"><span>{label}</span>{control}</label>'


def render_case(case):
    mutations = set(case.get("mutations") or [])
    fields = list(case["fields"])
    if "reordered" in mutations:
        random.Random(int(case.get("layout_seed") or 0)).shuffle(fields)
    controls = "".join(render_control(f, mutations, i) for i, f in enumerate(fields))
    if "decoy_controls" in mutations:
        decoy = {"name": "legacy_reference", "label": "Old reference (do not use)",
                 "kind": "text", "required": False, "value": ""}
        controls = render_control(decoy, {"hostile_defaults"}, 90) + controls
    if "nested_section" in mutations:
        controls = ("<details open><summary>Request details</summary>"
                    "<fieldset><legend>Information for this request</legend>" +
                    controls + "</fieldset></details>")
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
<form id="scenario-form">{controls}<button id="submit" type="submit">{submit}</button></form>
<div id="receipt" role="status" hidden></div></main><script>
const scenarioForm = document.getElementById('scenario-form');
const receiptElement = document.getElementById('receipt');
scenarioForm.addEventListener('submit', async (event) => {{
 event.preventDefault(); const payload = {{}};
 for (const el of scenarioForm.elements) {{ if (!el.name) continue; payload[el.name] = el.type === 'checkbox' ? el.checked : el.value; }}
 {"await new Promise(resolve => setTimeout(resolve, 650));" if "async_validation" in mutations else ""}
 const response = await fetch('/complete/{slug}', {{method:'POST', headers:{{'Content-Type':'application/json'}}, body:JSON.stringify(payload)}});
 const result = await response.json(); scenarioForm.hidden = true; receiptElement.hidden = false;
 const evidence = Object.entries(payload).map(([key, value]) => key + ': ' + String(value)).join(' · ');
 receiptElement.textContent = result.ok ? 'Submitted successfully. Confirmation #' + result.reference + '. ' + evidence : 'Please correct the highlighted fields.';
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


def provision_owner():
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
    return {"owner_ref": owner_ref, "legacy": legacy, "auth": auth_token}


def pair_registered_agent(identity, agent):
    headers = {"Authorization": identity["auth"], "Content-Type": "application/json"}
    expect(requests.patch(f"{PB}/api/collections/agents/records/{agent['record_id']}",
                          headers=headers, json={"owner": identity["legacy"],
                                                "owner_ref": identity["owner_ref"],
                                                "paired": True}, timeout=10),
           200, "agent pairing")
    return {**identity, **agent}


def wait_for_registered_agent(rig_tag, timeout=30):
    deadline = time.time() + timeout
    headers = {"X-Anticipy-Token": SERVICE_TOKEN}
    query = urllib.parse.urlencode({
        "filter": f'browser~"rig/{rig_tag}"', "sort": "-created", "perPage": 1,
    })
    while time.time() < deadline:
        response = requests.get(
            f"{PB}/api/collections/agents/records?{query}",
            headers=headers, timeout=10,
        )
        if response.ok:
            items = response.json().get("items") or []
            if items:
                return {"agent_id": items[0]["agent_id"],
                        "record_id": items[0]["id"]}
        time.sleep(1)
    raise RuntimeError("fresh extension did not register its own identity")


def queue_case(case, identity):
    # Fixed legacy cases intentionally hand the browser structured facts. A
    # full-chain generated case can set agent_facts={} so the extension must
    # recover every value from the brain's goal/source instead of receiving
    # the hidden oracle through workflow metadata.
    facts = case.get("agent_facts")
    if facts is None:
        facts = {f["name"]: f["value"] for f in case["fields"]}
    approved_scope = case.get("approved_scope") or case["task"]
    plan = new_plan(owner_ref=identity["owner_ref"],
                    lineage_key=f"day-zero:{case['slug']}:{uuid.uuid4()}",
                    goal=case["task"], consequence=Consequence.CONSEQUENTIAL,
                    source_event_id=f"scenario:{case['slug']}", facts=facts,
                    authority_text=case.get("authority_text") or approved_scope)
    plan = approve(plan, expected_version=plan.version,
                   owner_words=f"Run the {case['slug']} day-zero proof")
    params = {"task": case["task"], "start_url": f"{SITE}/case/{case['slug']}",
              "authorized": True, "approved_scope": approved_scope, **facts}
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
    last_row = {}
    while time.time() < deadline:
        try:
            row = requests.get(f"{PB}/api/collections/jobs/records/{job_id}",
                               headers=headers, timeout=10).json()
            last_row = row
        except requests.RequestException:
            # A disposable PocketBase or its Railway-env wrapper can restart
            # between two polls. That is neither a product result nor a reason
            # to discard every already-completed browser action in the cohort.
            time.sleep(1)
            continue
        if row.get("status") in {"done", "failed", "needs_user", "cancelled"}:
            return row
        time.sleep(1)
    try:
        return requests.get(f"{PB}/api/collections/jobs/records/{job_id}",
                            headers=headers, timeout=10).json()
    except requests.RequestException:
        return {**last_row, "status": "infrastructure_unreachable",
                "result": "certification backend stayed unreachable until timeout"}


DATE_FIELD_NAMES = {
    "birth", "date", "day", "end", "expiry", "renewal", "start", "travel",
}
TIME_FIELD_NAMES = {"time"}


def _date_value(value, today):
    text = " ".join(str(value or "").strip().casefold().split())
    try:
        return date.fromisoformat(text)
    except ValueError:
        pass
    if text == "tomorrow":
        return today + timedelta(days=1)
    weekdays = {name.casefold(): index for index, name in enumerate(
        ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"))}
    weekday = text.removeprefix("next ")
    if weekday in weekdays:
        offset = (weekdays[weekday] - today.weekday()) % 7 or 7
        return today + timedelta(days=offset)
    for fmt in ("%B %d, %Y", "%B %d %Y", "%B %d"):
        try:
            parsed = datetime.strptime(text.title(), fmt).date()
            if fmt == "%B %d":
                parsed = parsed.replace(year=today.year)
                if parsed < today:
                    parsed = parsed.replace(year=today.year + 1)
            return parsed
        except ValueError:
            pass
    return None


def _time_value(value):
    text = " ".join(str(value or "").strip().upper().split())
    for fmt in ("%I:%M %p", "%I %p", "%H:%M"):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.hour * 60 + parsed.minute
        except ValueError:
            pass
    return None


def _decimal_value(value):
    text = str(value or "").strip().replace("$", "").replace(",", "")
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _ordered_subsequence(needle, haystack):
    if not needle:
        return False
    at = 0
    for token in haystack:
        if token == needle[at]:
            at += 1
            if at == len(needle):
                return True
    return False


def _number_tokens(tokens):
    """Normalize spoken small numbers only for compact semantic controls."""
    number_words = {
        "zero": "0", "one": "1", "two": "2", "three": "3",
        "four": "4", "five": "5", "six": "6", "seven": "7",
        "eight": "8", "nine": "9", "ten": "10", "eleven": "11",
        "twelve": "12",
    }
    return [number_words.get(token, token) for token in tokens]


def _grounded_affirmed_contrast(got, expected, authority, soft):
    """Accept owner-authored ``X, not Y`` only when X is the expected choice."""
    negations = {"no", "not", "never", "without", "dont", "instead"}
    pivots = [index for index, token in enumerate(got) if token in negations]
    if len(pivots) != 1:
        return False
    pivot = pivots[0]
    before, after = got[:pivot], got[pivot + 1:]
    if not after or not _ordered_subsequence(expected, before):
        return False
    if _ordered_subsequence(expected, after):
        return False
    authority_core = _number_tokens([
        token for token in re.findall(
            r"[a-z0-9]+", str(authority or "").casefold())
        if token not in soft
    ])
    # Grounding is contiguous so unrelated words from different clauses cannot
    # be stitched into a convenient contrast by the verifier.
    return any(authority_core[start:start + len(got)] == got
               for start in range(len(authority_core) - len(got) + 1))


def _compact_semantic_field(spec):
    """Is this a short category/outcome, rather than an identity or prose?"""
    identity = " ".join(re.findall(
        r"[a-z0-9]+", f"{spec.get('name', '')} {spec.get('label', '')}".casefold()))
    return bool(re.search(
        r"\b(problem|service|method|resolution|effective|when|category|plan|"
        r"priority|status|type|choice|term|speed|risk|remedy|format|track|"
        r"program|facility|dealer|shop)\b", identity))


def _values_equal(spec, got, today, known_fields=(), authority=""):
    expected = spec["value"]
    if isinstance(expected, bool):
        return got is expected
    name, kind = spec["name"], spec.get("kind", "text")
    if kind == "date" or name in DATE_FIELD_NAMES:
        expected_date, got_date = _date_value(expected, today), _date_value(got, today)
        if expected_date is not None or got_date is not None:
            return expected_date is not None and expected_date == got_date
    if kind == "time" or name in TIME_FIELD_NAMES:
        expected_time, got_time = _time_value(expected), _time_value(got)
        if expected_time is not None or got_time is not None:
            return expected_time is not None and expected_time == got_time
    if kind == "number":
        expected_number, got_number = _decimal_value(expected), _decimal_value(got)
        if expected_number is not None or got_number is not None:
            return expected_number is not None and expected_number == got_number
    if kind == "tel" or name == "phone":
        return "".join(filter(str.isdigit, str(got))) == "".join(filter(str.isdigit, str(expected)))
    got_text = str(got or "").strip().casefold()
    expected_text = str(expected).strip().casefold()
    if got_text == expected_text:
        return True
    # Form fields often phrase the selected outcome as an instruction
    # ("request a corrected bill") while the option/oracle stores the noun
    # phrase ("Corrected bill"). Remove only semantically empty UI verbs and
    # articles; negations and any additional outcome remain mismatches.
    if name not in {"message", "body", "details", "issue", "summary", "purpose"}:
        soft = {"a", "an", "and", "against", "choose", "for", "from", "of",
                "on", "please", "request", "requested", "select", "the", "to", "with"}
        got_core = [token for token in re.findall(r"[a-z0-9]+", got_text) if token not in soft]
        expected_core = [token for token in re.findall(r"[a-z0-9]+", expected_text) if token not in soft]
        if bool(expected_core) and got_core == expected_core:
            return True
        # Text-rendered categorical controls have no page option to define a
        # canonical spelling. Judge their meaning, not an arbitrary template
        # string: a short answer may omit redundant category context, or may
        # include up to three EXTRA owner-authored context words. Identity and
        # prose fields remain strict. Negation never becomes equivalent.
        if _compact_semantic_field(spec) and got_core and expected_core:
            negations = {"no", "not", "never", "without", "dont", "instead"}
            semantic_got = _number_tokens(got_core)
            semantic_expected = _number_tokens(expected_core)
            if _grounded_affirmed_contrast(
                    semantic_got, semantic_expected, authority, soft):
                return True
            if not (negations & (set(semantic_got) ^ set(semantic_expected))):
                if _ordered_subsequence(semantic_got, semantic_expected):
                    return True
                if (_ordered_subsequence(semantic_expected, semantic_got)
                        and len(semantic_got) - len(semantic_expected) <= 3):
                    authority_tokens = set(_number_tokens(re.findall(
                        r"[a-z0-9]+", str(authority or "").casefold())))
                    extras = [token for token in semantic_got
                              if token not in set(semantic_expected)]
                    if extras and all(token in authority_tokens for token in extras):
                        return True
        # A portal can echo its own field noun into the value: field “Trip”
        # stores “Science Centre trip”, while the canonical value is “Science
        # Centre”. Remove only surplus tokens copied from this exact label;
        # arbitrary extra outcomes, names, numbers and negations still fail.
        label_tokens = set(re.findall(
            r"[a-z0-9]+", f"{name} {spec.get('label', '')}".casefold()))
        without_label_echo = [token for token in got_core
                              if token not in label_tokens
                              or token in expected_core]
        if bool(expected_core) and without_label_echo == expected_core:
            return True
        # A free-text portal field may redundantly include other exact values
        # from the same form ("Corrected invoice for INV-52192 / PO-3439").
        # Accept that only when the expected phrase remains contiguous and
        # every extra token is another oracle field value. New outcomes such
        # as "refund", negations, invented ids and changed numbers still fail.
        starts = range(len(without_label_echo) - len(expected_core) + 1)
        contains_expected = any(
            without_label_echo[start:start + len(expected_core)] == expected_core
            for start in starts)
        known_tokens = set()
        for field in known_fields:
            value = field.get("value")
            if isinstance(value, bool):
                continue
            known_tokens.update(token for token in re.findall(
                r"[a-z0-9]+", str(value).casefold()) if token not in soft)
        return (contains_expected and bool(known_tokens)
                and set(without_label_echo) <= known_tokens | label_tokens)
    return False


def values_match(case, actual, today=None):
    today = today or date.today()
    differences = []
    for spec in case["fields"]:
        expected = spec["value"]
        got = actual.get(spec["name"])
        if not _values_equal(spec, got, today, case["fields"],
                             case.get("authority_text") or case.get("approved_scope") or ""):
            differences.append(f"{spec['name']}={got!r} expected {expected!r}")
    return differences


def run_cases(cases, output=None, headless=False):
    global CASES_BY_SLUG
    output = Path(output) if output else ROOT / "work" / "day-zero-20-results.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    CASES_BY_SLUG = {case["slug"]: case for case in cases}
    expect(requests.get(f"{PB}/api/health", timeout=5), 200, "backend health")
    identity = provision_owner()
    server = ThreadedServer(("127.0.0.1", SITE_PORT), SiteHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    results = []
    profile_dir = tempfile.mkdtemp(prefix="anticipy-day-zero-")
    rig_work = ROOT / "work"
    rig_work.mkdir(parents=True, exist_ok=True)
    # Keep the unpacked extension under the repository. macOS/Chromium can
    # stall extension startup when an unpacked build lives in the per-process
    # /var/folders tree, while the same bytes at a stable user path load
    # immediately (the way the customer package does).
    rig_extension_dir = tempfile.mkdtemp(
        prefix="anticipy-rig-extension-", dir=rig_work)
    # Chromium's sandboxed extension loader must be able to traverse the
    # unpacked root. tempfile intentionally creates 0700 directories, which
    # makes Chrome wait forever during startup on macOS instead of reporting a
    # clean load error.
    os.chmod(rig_extension_dir, 0o755)
    rig_tag = uuid.uuid4().hex
    shutil.copytree(EXTENSION, rig_extension_dir, dirs_exist_ok=True)
    production_base = "https://api.anticipy.ai"
    # A fresh install must register itself, exactly as the shipped extension
    # does. Point only this disposable copy at the disposable backend before
    # launch, so the proof never injects credentials or touches production.
    for relative in ("background.js",):
        target = Path(rig_extension_dir) / relative
        source = target.read_text()
        if production_base not in source:
            raise RuntimeError(f"rig backend placeholder missing from {relative}")
        target.write_text(source.replace(production_base, PB))
    background = Path(rig_extension_dir) / "background.js"
    source = background.read_text()
    registration_bundle = (
        "agentId, agentToken, recordId: rec.id, pairCode, "
        "agentCredentialInstalled: true,"
    )
    if source.count(registration_bundle) != 1:
        raise RuntimeError("rig registration bundle changed")
    # The real development override is an extension-local backendUrl. Add it
    # to the same successful registration write the fresh install already
    # performs; no identity, model credential, owner fact, or oracle is
    # supplied by the harness.
    source = source.replace(
        registration_bundle,
        registration_bundle + " backendUrl: DEFAULT_BASE,",
    )
    version_marker = "ext/${chrome.runtime.getManifest().version}"
    if source.count(version_marker) != 2:
        raise RuntimeError("rig browser version markers changed")
    background.write_text(source.replace(
        version_marker, f"{version_marker} rig/{rig_tag}"))
    try:
        with sync_playwright() as playwright:
            executable = browser_executable()
            launch_options = {"executable_path": executable} if executable else {}
            if headless and not executable:
                # Playwright ≥1.49 answers headless=True with its
                # "headless shell" build, which does not run MV3
                # extensions at all: the worker silently never starts
                # (observed on Chromium 148, 2026-08-15). channel forces
                # the FULL Chromium in new-headless mode, where the same
                # extension starts in under a second.
                launch_options["channel"] = "chromium"
            context = playwright.chromium.launch_persistent_context(
                profile_dir, headless=headless, **launch_options,
                args=[f"--disable-extensions-except={rig_extension_dir}",
                      f"--load-extension={rig_extension_dir}"],
            )
            print("SETUP: isolated Chrome launched", flush=True)
            context.new_page().goto("about:blank")
            worker = None
            for _ in range(30):
                if context.service_workers:
                    worker = context.service_workers[0]
                    break
                time.sleep(1)
            if worker is None:
                raise RuntimeError("extension service worker did not start")
            print("SETUP: packaged extension started", flush=True)
            worker.on("console", lambda message: print(
                f"EXTENSION {message.type}: {message.text}", flush=True))
            # A real day-zero customer has the pairing page open in front of
            # them, and that page's ping is the worker's only reliable wake in
            # a brand-new profile: Chrome was probed (2026-08-14) creating NO
            # alarms at all in a fresh install, which left the worker deaf and
            # every job parked at "queued". The rig holds the same page open a
            # customer does — this is fidelity, not a cheat.
            extension_id = worker.url.split("/")[2]
            context.new_page().goto(
                f"chrome-extension://{extension_id}/onboarding.html")
            print("SETUP: pairing page open (worker wake source)", flush=True)
            # Pair the identity Chrome itself created. The disposable build's
            # unique browser marker lets the backend identify this exact fresh
            # install without debugging or mutating its private local storage.
            identity = pair_registered_agent(
                identity, wait_for_registered_agent(rig_tag))
            print("SETUP: fresh extension registered and paired", flush=True)
            agent_model = vision_model = "server-selected"
            for index, case in enumerate(cases, 1):
                with SITE_LOCK:
                    SITE_STATE.pop(case["slug"], None)
                job = queue_case(case, identity)
                print(f"RUN {index:02d}/{len(cases):02d} {case['slug']}", flush=True)
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
                note = ("stored verified form values + verified receipt" if ok else
                        f"status={row.get('status')} differences={differences} "
                        f"result={(row.get('result') or '')[:180]!r}")
                results.append({"scenario": case["slug"], "ok": ok,
                                "seconds": round(time.time() - started, 1),
                                "note": note, "job_id": job["id"]})
                checkpoint_passed = sum(1 for result in results if result["ok"])
                output.write_text(json.dumps({
                    "model": agent_model, "model_transport": "paired-backend-proxy",
                    "results": results,
                    "passed": checkpoint_passed, "total": len(results),
                    "complete": False, "output": str(output),
                }, indent=2))
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
        shutil.rmtree(profile_dir, ignore_errors=True)
        shutil.rmtree(rig_extension_dir, ignore_errors=True)

    summary = {"model": agent_model, "model_transport": "paired-backend-proxy",
               "results": results}
    passed = sum(1 for r in results if r["ok"])
    print(f"\nDAY-ZERO 20: {passed}/{len(results)} passed; evidence: {output}")
    summary.update({"passed": passed, "total": len(results),
                    "complete": True, "output": str(output)})
    output.write_text(json.dumps(summary, indent=2))
    return summary


def main():
    wanted = [x for x in sys.argv[1:] if x in CASES_BY_SLUG]
    cases = [CASES_BY_SLUG[x] for x in wanted] if wanted else CASES
    summary = run_cases(cases)
    raise SystemExit(0 if summary["passed"] == summary["total"] else 1)


if __name__ == "__main__":
    main()
