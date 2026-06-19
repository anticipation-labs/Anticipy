"""GATE C: onboarding auto-LEARNS the owner's people from already-connected accounts.

The scan already reads calendar attendees + email correspondents for FACTS; this pins that it now
also surfaces the recurring PEOPLE (for the owner to confirm in the recap), and — the honesty
floor — that it invents nothing: a person who appears only ONCE is NOT surfaced (one shared
meeting is not a relationship), and a displayName is preferred over a derived-from-email name.

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_onboard_people_discovery.py
"""
import os

os.environ.setdefault("ANTICIPY_MODEL_PROVIDER", "stub")
os.environ.setdefault("ANTICIPY_HANDS_MODE", "mock")
os.environ.setdefault("ANTICIPY_NATIVE_BRIDGE_FALLBACK", "0")
os.environ.setdefault("ANTICIPY_VAULT_KEY", "test-master-key-do-not-use-in-prod")

from anticipy_engine.core.control_core import ControlCore  # noqa: E402

core = ControlCore()

# alice appears on 2 events (recurs), bob on 1 (does NOT recur). priya has a displayName.
CAL = {
    "events": [
        {"start": {"dateTime": "2026-06-20T15:00:00Z"},
         "attendees": [{"email": "owner@x.com", "self": True},
                       {"email": "alice.wong@acme.com"},
                       {"email": "priya@acme.com", "displayName": "Priya Patel"}]},
        {"start": {"dateTime": "2026-06-21T15:00:00Z"},
         "attendees": [{"email": "owner@x.com", "self": True},
                       {"email": "alice.wong@acme.com"}]},
        {"start": {"dateTime": "2026-06-22T15:00:00Z"},
         "attendees": [{"email": "owner@x.com", "self": True},
                       {"email": "bob@once.com"}]},
    ]
}
# carol corresponds twice by email; priya once by email (already 1 from calendar -> total 2).
EMAIL = {
    "emails": [
        {"from": "Carol Diaz <carol@beta.com>"},
        {"from": "carol@beta.com"},
        {"from": "Priya Patel <priya@acme.com>"},
    ]
}

people = core._extract_discovered_people(CAL, None, EMAIL)
by_email = {p["email"]: p for p in people}

fails = []


def check(cond, msg):
    if not cond:
        fails.append(msg)


# alice recurs on the calendar (2) -> surfaced, name derived from email local part
check("alice.wong@acme.com" in by_email, "alice (2 events) NOT surfaced")
if "alice.wong@acme.com" in by_email:
    check(by_email["alice.wong@acme.com"]["count"] == 2, "alice count != 2")
    check(by_email["alice.wong@acme.com"]["name"] == "Alice Wong",
          f"alice name not prettified from email: {by_email['alice.wong@acme.com']['name']!r}")

# carol corresponds twice by email -> surfaced, displayName preferred
check("carol@beta.com" in by_email, "carol (2 threads) NOT surfaced")
if "carol@beta.com" in by_email:
    check(by_email["carol@beta.com"]["name"] == "Carol Diaz",
          f"carol displayName not used: {by_email['carol@beta.com']['name']!r}")

# priya appears once on calendar + once in email = 2 total -> surfaced with displayName
check("priya@acme.com" in by_email, "priya (cal+email = 2) NOT surfaced")
if "priya@acme.com" in by_email:
    check(by_email["priya@acme.com"]["name"] == "Priya Patel", "priya displayName not used")

# THE HONESTY FLOOR: bob appears only once -> must NOT be invented as a relationship
check("bob@once.com" not in by_email, "bob (1 event) WRONGLY surfaced — invented a relationship")

# nothing surfaced when there's nothing real to read
check(core._extract_discovered_people(None, None, None) == [], "empty reads should surface no people")
check(core._extract_discovered_people({"events": []}, None, {"emails": []}) == [],
      "thin reads should surface no people")

if fails:
    for f in fails:
        print("FAIL:", f)
    raise SystemExit(1)
print(f"PASS onboard_people_discovery: surfaced {sorted(by_email)} (bob@once.com correctly excluded)")
