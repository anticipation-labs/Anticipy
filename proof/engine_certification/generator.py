from __future__ import annotations

import hashlib
import json
from pathlib import Path
import random
import re
import secrets
import subprocess
from typing import Any


ROOT = Path(__file__).resolve().parents[2]

FIRST = ["Maya", "Jordan", "Priya", "Theo", "Nora", "Malik", "Sofia", "Jonah"]
LAST = ["Chen", "Patel", "Morgan", "Reyes", "Okafor", "Kim", "Singh", "Martin"]
PLACES = [
    "Harbour & Pine", "Juniper Room", "Northline Social", "Maple & Stone",
    "Cedar House", "Glasswater Kitchen", "Lighthouse Table", "Copper Finch",
]
VET_CLINICS = [
    "Kitsilano Animal Clinic", "Cambie Veterinary Hospital",
    "Granville Island Veterinary", "North Shore Pet Hospital",
]
DENTAL_CLINICS = [
    "West Coast Dental", "False Creek Dental Centre",
    "Cambie Village Dental", "Harbourview Dental",
]
DEALERS = [
    "OpenRoad Honda", "Destination Toyota", "Carter GM",
    "Dueck Auto Group",
]
GLASS_SHOPS = [
    "Broco Glass", "Speedy Glass", "All-West Glass", "NOVUS Glass",
]
CITIES = ["Vancouver", "Burnaby", "Richmond", "Victoria", "Surrey", "Coquitlam"]
TIMES = ["10:30 AM", "12:15 PM", "2:40 PM", "4:20 PM", "6:45 PM", "8:10 PM"]
DAYS = ["tomorrow", "Friday", "Saturday", "next Tuesday", "August 18", "September 4"]
ITEMS = [
    "ceramic lamp", "standing desk motor", "espresso grinder", "air purifier",
    "carry-on suitcase", "induction kettle", "wireless keyboard", "desk chair",
]
SERVICES = ["CloudLedger", "StudioBox", "NorthGrid", "ParcelPilot", "TeamCanvas"]


def _fingerprint() -> dict[str, Any]:
    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=ROOT, text=True, capture_output=True, check=True
        ).stdout.strip()

    dirty = git("status", "--porcelain")
    tracked = subprocess.run(
        ["git", "diff", "--binary", "HEAD"], cwd=ROOT, capture_output=True, check=True
    ).stdout
    return {
        "commit": git("rev-parse", "HEAD"),
        "dirty": bool(dirty),
        "candidate_sha256": hashlib.sha256(
            git("rev-parse", "HEAD").encode() + b"\0" + tracked
        ).hexdigest(),
    }


def _field(name: str, label: str, value: Any, kind: str = "text",
           options: list[str] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "label": label,
        "value": value,
        "kind": kind,
        "options": options or [],
    }


def _task(rng: random.Random, domain: str) -> dict[str, Any]:
    first, last = rng.choice(FIRST), rng.choice(LAST)
    full = f"{first} {last}"
    place, city = rng.choice(PLACES), rng.choice(CITIES)
    vet_clinic = rng.choice(VET_CLINICS)
    dental_clinic = rng.choice(DENTAL_CLINICS)
    dealer = rng.choice(DEALERS)
    glass_shop = rng.choice(GLASS_SHOPS)
    day, at = rng.choice(DAYS), rng.choice(TIMES)
    count = rng.randint(2, 7)
    item, service = rng.choice(ITEMS), rng.choice(SERVICES)
    suffix = rng.randint(10000, 99999)
    amount = f"{rng.randint(60, 950)}.{rng.randint(0, 99):02d}"
    usual = f"{rng.randint(30, 120)}.{rng.randint(0, 99):02d}"

    if domain == "reservation":
        goal = f"Book {place} in {city} for {count} on {day} at {at}"
        fields = [
            _field("venue", "Restaurant", place), _field("city", "City", city),
            _field("party", "Number of guests", str(count), "number"),
            _field("day", "Day", day), _field("time", "Time", at),
        ]
    elif domain == "maintenance":
        unit = f"{rng.randint(3, 28)}{rng.choice('ABC')}"
        issue = rng.choice(["sink leaking under the cabinet", "bedroom outlet sparking", "radiator staying cold"])
        goal = f"Submit an urgent maintenance request for unit {unit}: {issue}; allow entry if nobody is home"
        fields = [_field("unit", "Apartment", unit), _field("issue", "Problem", issue, "textarea"),
                  _field("urgent", "Urgent", True, "checkbox"), _field("entry", "Allow entry", True, "checkbox")]
    elif domain == "bill_dispute":
        account = f"NG-{suffix}"
        goal = f"Dispute the {service} bill on account {account}: charged ${amount}, usual ${usual}; request a corrected bill"
        fields = [_field("account", "Account number", account), _field("charged", "Amount charged", amount),
                  _field("usual", "Usual amount", usual), _field("resolution", "Requested resolution", "Corrected bill")]
    elif domain == "replacement":
        order = f"PK-{suffix}"
        goal = f"Request a replacement, not a refund, for the {item} in order {order} because it arrived damaged"
        fields = [_field("order", "Order number", order), _field("item", "Item", item),
                  _field("problem", "Problem", "Arrived damaged"), _field("resolution", "Resolution", "Replacement")]
    elif domain == "warranty":
        serial = f"SN-{rng.choice('ABCDEFGH')}{suffix}"
        issue = rng.choice(["screen flickers after sleep", "motor stops under load", "battery will not charge"])
        goal = f"Open a mail-in warranty repair for serial {serial}: {issue}"
        fields = [_field("serial", "Serial number", serial), _field("issue", "Describe the fault", issue, "textarea"),
                  _field("service", "Service method", "Mail-in repair")]
    elif domain == "recall":
        campaign = f"R{rng.randint(20, 29)}-{rng.randint(100, 999)}"
        goal = f"Schedule recall {campaign} for vehicle VIN 1HGCM82633A{suffix} at {dealer} on {day} at {at}"
        fields = [_field("campaign", "Recall campaign", campaign), _field("vin", "VIN", f"1HGCM82633A{suffix}"),
                  _field("dealer", "Dealer", dealer), _field("day", "Date", day), _field("time", "Time", at)]
    elif domain == "subscription":
        old, new = rng.randint(12, 40), rng.randint(2, 11)
        goal = f"Reduce the Anticipy workspace on {service} from {old} seats to {new} at renewal and keep the Pro plan"
        fields = [_field("workspace", "Workspace", "Anticipy"), _field("seats", "Seats", str(new), "number"),
                  _field("effective", "Effective", "At renewal"), _field("plan", "Plan", "Pro")]
    elif domain == "conference":
        title = rng.choice(["Agents That Earn Trust", "Ambient AI Without Surprises", "Evidence Before Automation"])
        goal = f"Submit {full}'s talk '{title}' to the Applied AI track as a 30-minute session"
        fields = [_field("speaker", "Speaker", full), _field("title", "Talk title", title),
                  _field("track", "Track", "Applied AI"), _field("format", "Format", "30-minute session")]
    elif domain == "parking":
        unit = str(rng.randint(301, 2804)); plate = f"{rng.choice('ABCDEFGH')}{rng.randint(1,9)}M {rng.randint(100,999)}"
        goal = f"Register {full}'s {plate} for guest parking at unit {unit} on {day} from 6 PM to 11 PM"
        fields = [_field("guest", "Guest", full), _field("plate", "Plate", plate),
                  _field("unit", "Unit", unit), _field("day", "Visit date", day), _field("window", "Window", "6 PM to 11 PM")]
    elif domain == "school":
        child = f"{rng.choice(FIRST)} {last}"
        goal = f"Give permission for {child} to attend the Science Centre trip on {day}; emergency contact {full} at +1 604 555 {rng.randint(1000,9999)}"
        phone = goal.rsplit(" ", 1)[-1]
        fields = [_field("student", "Student", child), _field("trip", "Trip", "Science Centre"),
                  _field("day", "Date", day), _field("contact", "Emergency contact", full),
                  _field("phone", "Phone", "+1 604 555 " + phone), _field("consent", "I give permission", True, "checkbox")]
    elif domain == "vet":
        pet = rng.choice(["Luna", "Miso", "Archie", "Pepper", "Cleo"])
        goal = f"Book {pet}, a dog, for a rabies vaccination at {vet_clinic} on {day} at {at}"
        fields = [_field("pet", "Pet name", pet), _field("species", "Species", "Dog"),
                  _field("service", "Visit reason", "Rabies vaccination"), _field("clinic", "Clinic", vet_clinic),
                  _field("day", "Date", day), _field("time", "Time", at)]
    elif domain == "insurance":
        policy = f"AUTO-{suffix}"
        goal = f"Open a windshield claim on policy {policy}: highway stone caused a 20 cm crack in {city} on {day}; use {glass_shop} for repair"
        fields = [_field("policy", "Policy", policy), _field("damage", "Damage", "Highway stone caused a 20 cm crack"),
                  _field("city", "Location", city), _field("day", "Date", day), _field("shop", "Repair shop", glass_shop)]
    elif domain == "expense":
        goal = f"Submit a ${amount} client-meal expense from {place} dated {day}, category Meals, purpose investor product review"
        fields = [_field("merchant", "Merchant", place), _field("amount", "Amount", amount),
                  _field("day", "Date", day), _field("category", "Category", "Meals"),
                  _field("purpose", "Business purpose", "Investor product review")]
    elif domain == "accessibility":
        goal = f"Request front-row seating and live captions for {full} at Demo Day on {day}"
        fields = [_field("attendee", "Attendee", full), _field("event", "Event", "Demo Day"),
                  _field("day", "Date", day), _field("request", "Accommodation", "Front-row seating and live captions")]
    elif domain == "utility_move":
        old = f"{rng.randint(10,999)} Seaside Avenue"; new = f"{rng.randint(10,999)} Marine Drive"
        goal = f"Move electricity and water from {old} to {new} on {day}; keep the old address active through the day before"
        fields = [_field("old", "Current address", old), _field("new", "New address", new),
                  _field("services", "Services", "Electricity and water"), _field("day", "Move date", day)]
    elif domain == "license":
        license_id = f"ARCH-{suffix}"
        goal = f"Renew professional license {license_id} for one year and confirm continuing education is complete"
        fields = [_field("license", "License number", license_id), _field("term", "Renewal term", "1 year"),
                  _field("education", "Education complete", True, "checkbox")]
    elif domain == "invoice":
        invoice = f"INV-{suffix}"; po = f"PO-{rng.randint(1000,9999)}"
        agreed = f"{rng.randint(1000,9000)}.00"; billed = f"{int(float(agreed))+1000}.00"
        goal = f"Dispute invoice {invoice} against {po}: billed ${billed}, agreed ${agreed}; request a corrected invoice"
        fields = [_field("invoice", "Invoice", invoice), _field("po", "Purchase order", po),
                  _field("billed", "Billed", billed), _field("agreed", "Agreed", agreed),
                  _field("resolution", "Requested resolution", "Corrected invoice")]
    elif domain == "cancellation":
        member = f"MBR-{suffix}"
        goal = f"Cancel membership {member} at {service} at the end of the current billing period and request written confirmation"
        fields = [_field("member", "Membership", member), _field("effective", "When", "End of current billing period"),
                  _field("confirm", "Send confirmation", True, "checkbox")]
    elif domain == "appointment":
        goal = f"Schedule {full} for a dental cleaning at {dental_clinic} in {city} on {day} at {at}"
        fields = [_field("patient", "Patient", full), _field("service", "Appointment", "Dental cleaning"),
                  _field("clinic", "Clinic", dental_clinic), _field("city", "City", city),
                  _field("day", "Date", day), _field("time", "Time", at)]
    elif domain == "message":
        body = rng.choice(["The revised numbers are ready for review.", "I can meet after 3 PM tomorrow.", "Please use the final deck in the shared folder."])
        goal = f"Send {full} this exact message: {body}"
        fields = [_field("recipient", "To", full), _field("message", "Message", body, "textarea")]
    else:
        raise ValueError(domain)
    return {"domain": domain, "goal": goal, "fields": fields}


DOMAINS = [
    "reservation", "maintenance", "bill_dispute", "replacement", "warranty",
    "recall", "subscription", "conference", "parking", "school", "vet",
    "insurance", "expense", "accessibility", "utility_move", "license",
    "invoice", "cancellation", "appointment", "message",
]
ARCHETYPES = [
    "ambient_progressive", "direct_request", "correction", "dictation",
    "other_person_owns_it", "sarcasm", "memory_recall", "two_tasks",
]


def _corrected_value(rng: random.Random, field: dict[str, Any]) -> str:
    """Create a plausible spoken correction instead of synthetic suffixes."""
    old = str(field["value"])
    name = field["name"]
    people = [f"{first} {last}" for first in FIRST for last in LAST]
    pools = {
        "venue": PLACES,
        "merchant": PLACES,
        "city": CITIES,
        "dealer": DEALERS,
        "shop": GLASS_SHOPS,
        "clinic": VET_CLINICS + DENTAL_CLINICS,
        "day": DAYS,
        "time": TIMES,
        "pet": ["Luna", "Miso", "Archie", "Pepper", "Cleo"],
        "speaker": people,
        "guest": people,
        "student": people,
        "contact": people,
        "attendee": people,
        "patient": people,
        "recipient": people,
        "workspace": ["Anticipy", "Anticipy Labs", "Anticipy Demo"],
        "plan": ["Pro", "Business"],
        "effective": ["At renewal", "End of current billing period"],
    }
    options = [value for value in pools.get(name, []) if value != old]
    if options:
        return rng.choice(options)
    if name in ("old", "new") and re.fullmatch(r"\d+ .+", old):
        return re.sub(r"^\d+", str(rng.randint(10, 999)), old)
    if old.isdigit():
        return str(int(old) + rng.choice([1, 2]))
    # IDs and short codes are naturally corrected by one character; amounts
    # are naturally corrected numerically. Both retain realistic shape.
    if re.fullmatch(r"\d+\.\d{2}", old):
        return f"{float(old) + rng.choice([10, 25, 50]):.2f}"
    if old:
        replacement = "9" if old[-1] != "9" else "8"
        return old[:-1] + replacement
    return old


def _browser_spec(rng: random.Random, task: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": f"{task['domain'].replace('_', ' ').title()} Portal",
        "goal": task["goal"],
        "fields": task["fields"],
        "layout_seed": rng.getrandbits(64),
        "mutations": rng.sample(
            ["reordered", "decoy_controls", "async_validation",
             "nested_section", "hostile_defaults", "autocomplete"],
            k=rng.randint(1, 3),
        ),
    }


def _surface(rng: random.Random, task: dict[str, Any], archetype: str,
             case_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    goal = task["goal"]
    required = [str(f["value"]) for f in task["fields"] if f["value"] not in (True, False)]
    utterances: list[dict[str, Any]] = []
    expected_jobs = 1
    min_texts, max_texts = 0, 1
    answer_contains: list[str] = []

    if archetype == "ambient_progressive":
        midpoint = max(1, len(goal.split()) // 2)
        words = goal.split()
        utterances = [
            {"text": rng.choice(["good to see you, it's been a week", "okay there is a lot going on today"]), "speaker": "other"},
            {"text": "we should actually get this sorted: " + " ".join(words[:midpoint]), "speaker": "owner"},
            {"text": "yeah, agreed — " + " ".join(words[midpoint:]), "speaker": "owner"},
            {"text": rng.choice(["perfect, let's do that", "great, that's settled then"]), "speaker": "other"},
        ]
        min_texts = max_texts = 1
    elif archetype == "direct_request":
        utterances = [{"text": rng.choice(["Anticipy, ", "Can you ", "Please "]) + goal, "explicit": True, "speaker": "owner"}]
        min_texts, max_texts = 0, 1
    elif archetype == "correction":
        mutable = next((f for f in task["fields"] if f["kind"] in ("number", "text") and len(str(f["value"])) < 20), task["fields"][0])
        old = str(mutable["value"])
        new = _corrected_value(rng, mutable)
        original_goal = goal
        corrected_goal = goal.replace(old, new, 1)
        mutable["value"] = new
        required = [str(f["value"]) for f in task["fields"] if f["value"] not in (True, False)]
        utterances = [
            {"text": "Anticipy, " + original_goal, "explicit": True, "speaker": "owner"},
            {"text": f"Actually change {old} to {new}; keep everything else the same.", "explicit": True, "speaker": "owner"},
        ]
        task["goal"] = corrected_goal
        # One notice for the initial held action and one concise correction
        # acknowledgement are both reasonable. The hard invariants are one
        # surviving job and the corrected final values.
        max_texts = 2
    elif archetype == "dictation":
        utterances = [{"text": (
            "In the note I am writing to the team, explain that we are testing the complete product and include this example as quoted material only: "
            + goal + ". Then ask them to review the logs, compare the evidence, and tell me which layer dropped the request before anyone changes production."
        ), "speaker": "owner"}]
        expected_jobs = min_texts = max_texts = 0
        required = []
    elif archetype == "other_person_owns_it":
        utterances = [{"text": "Don't touch this one; I will handle it myself: " + goal, "speaker": "other:Jordan"}]
        expected_jobs = min_texts = max_texts = 0
        required = []
    elif archetype == "sarcasm":
        # Keep the oracle unambiguous. A sarcastic complaint that repeats a
        # fully specified real obligation can still be a legitimate signal
        # for a proactive assistant; expecting silence there would train the
        # evaluator's preference, not test an objective truth.
        topic = task["domain"].replace("_", " ")
        utterances = [{"text": f"Oh fantastic, another {topic} reminder — exactly what my day was missing.", "speaker": "owner"}]
        expected_jobs = min_texts = max_texts = 0
        required = []
    elif archetype == "memory_recall":
        code = str(rng.randint(100000, 999999))
        utterances = [
            {"text": f"For later, the pickup code for {task['domain']} is {code}.", "speaker": "owner"},
            {"text": f"Anticipy, what is the pickup code I just told you for {task['domain']}?", "explicit": True, "speaker": "owner"},
        ]
        expected_jobs = min_texts = max_texts = 0
        required = []
        answer_contains = [code]
    elif archetype == "two_tasks":
        second = _task(rng, rng.choice([d for d in DOMAINS if d != task["domain"]]))
        utterances = [
            {"text": "Anticipy, " + goal, "explicit": True, "speaker": "owner"},
            {"text": "Separate task, also " + second["goal"], "explicit": True, "speaker": "owner"},
        ]
        expected_jobs = 2
        required = []
        task["second_task"] = second
        max_texts = 2
    else:
        raise ValueError(archetype)

    browser_tasks = []
    if expected_jobs:
        browser_tasks.append(_browser_spec(rng, task))
        if task.get("second_task"):
            browser_tasks.append(_browser_spec(rng, task["second_task"]))

    # The phone's voice verdict only exists after the owner enrolls a
    # voiceprint, and enrollment is dormant in the shipped build — so half
    # of all stories run in day-one reality: NO verdict on any line, and the
    # brain must earn "whose errand is this" from the words alone. The other
    # half run post-enrollment, where the tagger says "owner" or "other" and
    # NEVER a name. A named label ("other:Jordan") was the answer key
    # leaking straight from this generator into the brain — the tester
    # answering its own exam. Caught by the owner, 2026-08-14.
    voice_enrolled = rng.random() < 0.5
    for utterance in utterances:
        if not voice_enrolled:
            utterance.pop("speaker", None)
        elif str(utterance.get("speaker", "")).startswith("other:"):
            utterance["speaker"] = "other"

    case = {
        "id": case_id,
        "archetype": archetype,
        "domain": task["domain"],
        "voice_enrolled": voice_enrolled,
        "utterances": utterances,
        "browser": browser_tasks[0] if browser_tasks else None,
        "browser_tasks": browser_tasks,
    }
    oracle = {
        "id": case_id,
        "expected_jobs": expected_jobs,
        "required_values": required,
        "forbidden_values": [],
        "min_notifications": min_texts,
        "max_notifications": max_texts,
        "answer_contains": answer_contains,
        "final_goal": task.get("goal"),
    }
    return case, oracle


def generate(count: int, cases_path: Path, oracle_path: Path,
             seed: int | None = None) -> dict[str, Any]:
    if count < 1:
        raise ValueError("count must be positive")
    seed = seed if seed is not None else secrets.randbits(128)
    rng = random.Random(seed)
    fingerprint = _fingerprint()
    cases, oracles = [], []
    for index in range(count):
        domain = DOMAINS[index % len(DOMAINS)]
        archetype = ARCHETYPES[(index // len(DOMAINS) + index) % len(ARCHETYPES)]
        nonce = rng.getrandbits(64)
        case_id = f"story-{index + 1:04d}-{nonce:016x}"
        case, oracle = _surface(rng, _task(rng, domain), archetype, case_id)
        cases.append(case)
        oracles.append(oracle)
    header = {
        "format": 1,
        "count": count,
        "seed_hex": f"{seed:032x}",
        "candidate": fingerprint,
    }
    cases_path.parent.mkdir(parents=True, exist_ok=True)
    cases_path.write_text(json.dumps({**header, "cases": cases}, indent=2) + "\n")
    oracle_path.write_text(json.dumps({**header, "oracles": oracles}, indent=2) + "\n")
    return header
