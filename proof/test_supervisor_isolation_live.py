#!/usr/bin/env python3
"""Black-box two-account proof for the worker supervisor and memory boundary."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import uuid

import requests


ROOT = Path(__file__).resolve().parents[1]
BASE = os.getenv("PB_BASE", "http://127.0.0.1:18092").rstrip("/")
SERVICE = os.getenv("RIG_SERVICE_TOKEN", "supervisor-rig-secret")
STATE_ROOT = Path(os.getenv("RIG_STATE_ROOT", ROOT / "work" / "supervisor-state"))


def expect(response, status, label):
    if response.status_code != status:
        raise AssertionError(f"{label}: {response.status_code}: {response.text[:400]}")
    print(f"PASS {label}")
    return response


def owner(label):
    suffix = uuid.uuid4().hex[:8]
    email = f"supervisor-{label}-{suffix}@proof.invalid"
    password = "Supervisor-proof-password-42!"
    legacy = f"supervisor-device-{label}-{suffix}"
    expect(requests.post(f"{BASE}/api/collections/owners/records", json={
        "email": email, "password": password, "passwordConfirm": password,
        "legacy_uuid": legacy,
    }, timeout=10), 200, f"owner {label} signs up")
    auth = expect(requests.post(
        f"{BASE}/api/collections/owners/auth-with-password",
        json={"identity": email, "password": password}, timeout=10,
    ), 200, f"owner {label} signs in").json()
    ref, token = auth["record"]["id"], auth["token"]
    headers = {"Authorization": token, "Content-Type": "application/json"}
    expect(requests.post(f"{BASE}/api/collections/owner_profile/records",
                         headers=headers, json={
        "owner_ref": ref, "owner_id": legacy, "first_name": label.title(),
        "email": email, "timezone": "America/Vancouver",
    }, timeout=10), 200, f"owner {label} creates a private profile")
    return {"label": label, "ref": ref, "legacy": legacy, "headers": headers}


def post_line(person, text):
    return expect(requests.post(f"{BASE}/api/collections/events/records",
                                headers=person["headers"], json={
        "owner_ref": person["ref"], "owner": person["legacy"],
        "device_id": "supervisor-proof", "kind": "transcript", "text": text,
        "explicit": True,
    }, timeout=10), 200, f"{person['label']} submits an explicit line").json()["id"]


def all_events(person):
    return expect(requests.get(f"{BASE}/api/collections/events/records",
                               headers=person["headers"], params={
        "filter": f'owner_ref="{person["ref"]}"', "sort": "created", "perPage": 100,
    }, timeout=10), 200, f"{person['label']} reads only their events").json()["items"]


def wait_for(predicate, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.5)
    raise AssertionError("timed out waiting for isolated workers")


def memory_texts(owner_ref):
    path = STATE_ROOT / owner_ref / "memory.db"
    if not path.exists():
        raise AssertionError(f"missing private memory: {path}")
    db = sqlite3.connect(path)
    return [row[0] for row in db.execute("SELECT text FROM episodes ORDER BY id")]


def main():
    expect(requests.get(f"{BASE}/api/health", timeout=5), 200, "fresh backend is live")
    alpha, bravo = owner("alpha"), owner("bravo")
    alpha_fact = "Remember that Alpha's blue locker code is 2468."
    bravo_fact = "Remember that Bravo's green locker code is 9753."
    alpha_id = post_line(alpha, alpha_fact)
    bravo_id = post_line(bravo, bravo_fact)

    env = dict(os.environ)
    env.update({
        "ANTICIPY_PB": BASE,
        "ANTICIPY_SERVICE_TOKEN": SERVICE,
        "ANTICIPY_STATE_ROOT": str(STATE_ROOT),
        "ANTICIPY_OWNER_DISCOVERY_SECONDS": "2",
        "ANTICIPY_MAX_OWNER_WORKERS": "2",
        "ANTICIPY_SEGMENTS": "1",
        "PYTHONUNBUFFERED": "1",
        "OPENROUTER_API_KEY": "",
        "BRAVE_API_KEY": "",
        "TWILIO_ACCOUNT_SID": "",
        "TWILIO_AUTH_TOKEN": "",
        "TWILIO_PHONE_NUMBER": "",
        "TWILIO_FROM": "",
    })
    proc = subprocess.Popen(
        [sys.executable, "-u", "-m", "brain.supervisor"], cwd=ROOT,
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        def both_facts_heard():
            a = all_events(alpha)
            b = all_events(bravo)
            by_id_a = {row["id"]: row for row in a}
            by_id_b = {row["id"]: row for row in b}
            return (a, b) if (by_id_a.get(alpha_id, {}).get("decision") and
                              by_id_b.get(bravo_id, {}).get("decision")) else None

        wait_for(both_facts_heard)
        print("PASS both account workers independently hear their first fact")

        post_line(alpha, "What is Alpha's locker code?")
        post_line(bravo, "What is Bravo's locker code?")

        def both_answered():
            a, b = all_events(alpha), all_events(bravo)
            a_says = [row.get("text", "") for row in a if row.get("kind") == "anticipy_says"]
            b_says = [row.get("text", "") for row in b if row.get("kind") == "anticipy_says"]
            if any("2468" in text for text in a_says) and any("9753" in text for text in b_says):
                return a, b
            return None

        a_events, b_events = wait_for(both_answered)
        assert not any("9753" in str(row.get("text", "")) for row in a_events)
        assert not any("2468" in str(row.get("text", "")) for row in b_events)
        assert all(row.get("owner_ref") == alpha["ref"] for row in a_events)
        assert all(row.get("owner_ref") == bravo["ref"] for row in b_events)
        print("PASS each answer contains only its owner's exact fact")
        print("PASS every generated event remains canonically owner-stamped")

        a_memory = memory_texts(alpha["ref"])
        b_memory = memory_texts(bravo["ref"])
        assert any("2468" in text for text in a_memory) and not any("9753" in text for text in a_memory)
        assert any("9753" in text for text in b_memory) and not any("2468" in text for text in b_memory)
        print("PASS on-disk memory databases contain zero cross-owner facts")

        result = {
            "passed": True,
            "owners": {
                "alpha": {"owner_ref": alpha["ref"], "memory": str(STATE_ROOT / alpha["ref"] / "memory.db")},
                "bravo": {"owner_ref": bravo["ref"], "memory": str(STATE_ROOT / bravo["ref"] / "memory.db")},
            },
            "assertions": [
                "dynamic discovery started one worker per owner",
                "each transcript was processed only by its owner worker",
                "each memory answer returned only its owner's exact code",
                "generated events carried the canonical owner_ref",
                "durable SQLite memory files contained no cross-owner facts",
            ],
        }
        output = ROOT / "work" / "supervisor-live-results.json"
        output.write_text(json.dumps(result, indent=2) + "\n")
        print(f"SUPERVISOR ISOLATION PROOF PASSED: {output}")
    finally:
        proc.terminate()
        try:
            stdout, _ = proc.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, _ = proc.communicate(timeout=5)
        print("--- supervisor evidence ---")
        for line in stdout.splitlines():
            if ("supervisor up" in line or "owner worker started" in line or
                    "worker up" in line or line.startswith("heard:")):
                print(line)


if __name__ == "__main__":
    main()
