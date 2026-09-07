"""Execute authored transcripts through local workerd and the real brain worker.

This measures ingestion, contextual decisions, persisted memory, questions and
queued work. It does NOT claim browser/provider completion; those need their
own stateful fixtures and effect receipts. No evaluator rubric enters the brain.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import secrets
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
STATE = ROOT / "work/audit"
BASE = "http://127.0.0.1:8787"


def isolated_network(event, args):
    if event == "socket.getaddrinfo":
        host = args[0]
        if host not in ("127.0.0.1", "localhost", "::1"):
            raise PermissionError("audit brain may resolve only loopback fixtures")
    elif event == "socket.connect":
        address = args[1]
        if isinstance(address, tuple) and not ipaddress.ip_address(address[0]).is_loopback:
            raise PermissionError("audit brain may connect only to loopback fixtures")
    elif event in ("subprocess.Popen", "os.system"):
        raise PermissionError("audit brain cannot launch an unisolated child")


def child():
    sys.addaudithook(isolated_network)
    from brain import llm, worker
    llm.OPENROUTER_URL = "http://127.0.0.1:8790/api/v1/chat/completions"
    # This is the production entry point, with its own polling, attribution,
    # segmentation, budgets, retry behavior, persistence and model decisions.
    worker.main()


def run_person(person, label, timeout):
    import requests
    from proof.audit.model_gateway import atomic_json

    run_dir = STATE / "transcripts" / label / person["id"]
    if run_dir.exists():
        raise SystemExit("run already exists; use a new label to preserve evidence")
    run_dir.mkdir(parents=True, mode=0o700)
    service = requests.Session()
    service.trust_env = False
    service.headers["X-Anticipy-Token"] = "local-development-service-token"

    def request(method, path, **kwargs):
        response = service.request(method, BASE + path, timeout=20, **kwargs)
        response.raise_for_status()
        return response.json() if response.content else None

    password = secrets.token_urlsafe(24)
    # Unique server-issued owner per execution: repeated runs cannot inherit
    # a previous lane's memory, jobs, profile or authorization.
    owner = request("POST", "/api/collections/owners/records", json={
        "email": f"{label}-{person['id']}@anticipy-test.invalid",
        "password": password, "passwordConfirm": password,
    })
    ref = owner["id"]
    auth = request("POST", "/api/collections/owners/auth-with-password", json={
        "identity": owner["email"], "password": password,
    })
    account = requests.Session()
    account.trust_env = False
    account.headers["Authorization"] = auth["token"]
    atomic_json(run_dir / "identity.json", {"owner_ref": ref, "token": auth["token"], "password": password})
    first, _, last = person["name"].partition(" ")
    request("POST", "/api/collections/owner_profile/records", json={
        "owner_ref": ref, "owner_id": ref, "name": person["name"],
        "first_name": first, "last_name": last, "email": owner["email"],
        "phone": person["phone"], "timezone": person["timezone"],
    })

    def event(text, kind, source, **extra):
        stamp = datetime.now(timezone.utc).isoformat()
        response = account.post(BASE + "/api/collections/events/records", json={
            "owner_ref": ref, "kind": kind, "text": text,
            "source": source, "device_id": "audit-typed-" + person["id"],
            "decision": "", "spoken_at": stamp, "capture_started_at": stamp,
            **extra,
        }, timeout=20)
        if not response.ok:
            raise RuntimeError(f"fixture event was rejected: {response.status_code} {response.text}")
        return response.json()

    imports = [event(person["history"][0]["text"], "profile", "interview", importance=5)]
    imports += [event("Imported address-book contact: " + json.dumps(contact), "profile", "import")
                for contact in person["contacts"]]
    imports += [event(person["history"][1]["text"], "profile", "import")]
    baseline_calls = {c["id"] for c in json.loads((STATE / "spend.json").read_text())["calls"]}
    env = {key: os.environ[key] for key in ("PATH", "HOME", "LANG", "TMPDIR") if key in os.environ}
    env.update({
        "PYTHONPATH": str(ROOT), "PYTHONUNBUFFERED": "1",
        "OPENROUTER_API_KEY": (STATE / "gateway-token").read_text().strip(),
        "ANTICIPY_PB": BASE, "ANTICIPY_OWNER_REF": ref, "ANTICIPY_OWNER_ID": ref,
        "ANTICIPY_SERVICE_TOKEN": "local-development-service-token",
        "ANTICIPY_SUPERVISED": "1", "ANTICIPY_SMS_PROVIDER": "mock",
        "ANTICIPY_MEMORY_DB": str(run_dir / "memory.db"),
        "ANTICIPY_CLOCK_STATE": str(run_dir / "clock_state.json"),
        "ANTICIPY_TZ": person["timezone"],
        "ANTICIPY_MODEL": "deepseek/deepseek-v3.2",
        "ANTICIPY_STRONG_MODEL": "google/gemini-3.1-pro-preview",
    })
    source_hash = hashlib.sha256(b"".join(p.read_bytes() for p in sorted((ROOT / "brain").glob("*.py")))).hexdigest()
    atomic_json(run_dir / "scenario.json", person)
    result = {"person_id": person["id"], "owner_ref": ref, "source_sha256": source_hash,
              "scenario_sha256": hashlib.sha256(json.dumps(person, sort_keys=True).encode()).hexdigest(),
              "scope": "local HTTP ingestion, real brain, real model, persisted memory and work; no browser or provider effects",
              "state": "running", "started_at": time.time()}
    atomic_json(run_dir / "result.json", result)
    started = time.monotonic()
    process = None
    try:
        with (run_dir / "worker.log").open("w") as log:
            process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--child"], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
            # Let the production startup/profile cadence operate unchanged.
            while True:
                rows = [request("GET", "/api/collections/events/records/" + row["id"]) for row in imports]
                if all(row.get("decision") for row in rows):
                    break
                if process.poll() is not None or time.monotonic() - started > 150:
                    raise RuntimeError("profile imports did not complete; inspect worker.log")
                time.sleep(2)
            transcript = event(person["transcript"]["text"], "transcript", "typed", explicit=True, speaker="owner")
            result["transcript_id"] = transcript["id"]
            heard_started = time.monotonic()
            while time.monotonic() - heard_started < timeout:
                row = request("GET", "/api/collections/events/records/" + transcript["id"])
                if row.get("decision") not in ("", "hearing", "processing", "claimed"):
                    result["transcript"] = row
                    result["state"] = "observed_needs_semantic_review"
                    break
                if process.poll() is not None:
                    raise RuntimeError("brain worker exited before a decision")
                time.sleep(2)
            else:
                raise RuntimeError("no finished decision before timeout")
            time.sleep(3)  # collect the app reply written after the decision stamp
    except Exception as error:
        result.update(state="infrastructure_or_runtime_failure", error=str(error))
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for collection in ("events", "jobs", "segments"):
            data = request("GET", f"/api/collections/{collection}/records", params={
                "filter": f'owner_ref="{ref}"', "perPage": 500, "sort": "created",
            })
            atomic_json(run_dir / (collection + ".json"), data)
        ledger = json.loads((STATE / "spend.json").read_text())
        calls = [c for c in ledger["calls"] if c["id"] not in baseline_calls]
        result.update(elapsed_seconds=round(time.monotonic() - started, 2),
                      model_calls=len(calls), call_ids=[c["id"] for c in calls],
                      observed_cost_usd=sum(c.get("cost_usd") or 0 for c in calls),
                      unresolved_reservations=sum(c["reserved_usd"] for c in calls if c.get("cost_usd") is None))
        if not calls or result["unresolved_reservations"] or any(c["state"] != "returned" for c in calls):
            result["state"] = "infrastructure_or_runtime_failure"
        atomic_json(run_dir / "result.json", result)
    print(json.dumps({k: result[k] for k in ("person_id", "state", "elapsed_seconds", "model_calls", "observed_cost_usd", "unresolved_reservations")}), flush=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--ids", default="10")
    parser.add_argument("--label", default="pilot-1")
    parser.add_argument("--timeout", type=int, default=150)
    args = parser.parse_args()
    if args.child:
        child()
    else:
        people = json.loads((ROOT / "proof/audit/corpus/people.json").read_text())["people"]
        selected = [int(i) for i in args.ids.split(",")]
        for index in selected:
            person = people[index - 1]
            if person["split"] == "held_out":
                raise SystemExit("held-out scenarios stay closed until development checks are complete")
            result = run_person(person, args.label, args.timeout)
            if result["state"] == "infrastructure_or_runtime_failure":
                raise SystemExit(2)
