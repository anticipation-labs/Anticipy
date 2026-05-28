#!/usr/bin/env python3
"""V7 verifier-first proposal: memory account+device scoping.

Cite: ANTICIPY_V7.md PART 0 (user-device engine, no fake receipts),
PART 1A item 4 (memory resolution), PART 4 (decisions tied to account
and device), PART 6 item 7 (no fixture account satisfies proof).

V7 gate guarded: V7.20 (no fake receipts, backdoors, stale proofs).
Motivates fixing engine/app/anticipy/memory.py (static USER_ID) and
engine/app/product/server.py (unscoped /api/memory reads).

Asserts:
  S1. /api/memory entries carry account_id + device_id + source + ts
      + confidence + kind + active + provenance.
  S2. Account A read does not see account B writes and vice versa.
  S3. Pronoun "her" resolves to A's Maya (not across accounts).
  S4. do_not_touch entry blocks the action on that target.

Cleans up probe rows in `finally`. Today every assertion is expected
to FAIL; after the frozen-path fix each must PASS.

Run: python3 state/v7/proposed_verifiers/verify_memory_account_device_scoping.py

Exit 0 = all pass, 1 = any fail. Verdict at
state/v7/proposed_verifier_runs/verify_memory_account_device_scoping/result.json.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any


SCHEMA = "anticipy.v7.proposed_verifier.memory_account_device_scoping"
ENGINE_URL = os.environ.get("ANTICIPY_ENGINE_URL", "http://127.0.0.1:8731")
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
OUT_DIR = REPO_ROOT / "state" / "v7" / "proposed_verifier_runs" \
    / "verify_memory_account_device_scoping"
OUT_FILE = OUT_DIR / "result.json"

REQUIRED_FIELDS = (
    "account_id",
    "device_id",
    "source",
    "timestamp",
    "confidence",
    "kind",
    "active",
    "provenance",
)


def now_z() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(
        microsecond=0
    ).isoformat().replace("+00:00", "Z")


def http_request(method: str, path: str, payload: dict | None = None,
                 timeout: float = 20.0) -> tuple[int, Any]:
    url = ENGINE_URL.rstrip("/") + path
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return exc.code, raw
    except urllib.error.URLError as exc:
        return 0, {"error": f"url_error: {exc.reason}"}
    except Exception as exc:
        return 0, {"error": f"{type(exc).__name__}: {exc}"}


def probe_tag(label: str) -> str:
    return f"V7_PROPOSED_VERIFIER_PROBE_{label}_{uuid.uuid4().hex[:10]}"


def list_memory() -> list[dict]:
    status, body = http_request("GET", "/api/memory")
    if status != 200 or not isinstance(body, dict):
        return []
    entries = body.get("entries")
    return entries if isinstance(entries, list) else []


def write_memory_via_inject(account_id: str, device_id: str, text: str) -> dict:
    payload = {"text": text, "account_id": account_id, "device_id": device_id}
    status, body = http_request("POST", "/api/listen/inject", payload, timeout=45.0)
    return {"status": status,
            "body": body if isinstance(body, (dict, list, str)) else str(body)}


def write_memory_scoped(account_id: str, device_id: str, kind: str, key: str,
                        value: str, source: str = "verifier-first-probe",
                        provenance: str = "manual_probe",
                        confidence: float = 1.0) -> dict:
    """Use the V7 scoped router if wired; otherwise fall back to /inject.

    Scoped router lives at engine/app/product/scoped_memory_endpoints.py.
    """
    payload = {"account_id": account_id, "device_id": device_id, "kind": kind,
               "key": key, "value": value, "source": source,
               "provenance": provenance, "confidence": confidence}
    status, body = http_request("POST", "/api/memory/write", payload)
    if status == 200:
        return {"path": "scoped_endpoint", "status": status, "body": body}
    inject = write_memory_via_inject(account_id, device_id, value)
    inject["path"] = "fallback_inject"
    return inject


def cleanup(probe_tags: list[str]) -> dict:
    """Best-effort cleanup of memory rows tagged with our sentinels."""
    removed: list[str] = []
    remaining: list[str] = []
    deleted_via: list[str] = []
    for tag in probe_tags:
        status, _ = http_request("POST", "/api/memory/delete",
                                  {"contains": tag}, timeout=10.0)
        if status == 200:
            deleted_via.append("scoped_endpoint")
            removed.append(tag)
            continue
        entries = list_memory()
        if not any(tag in str(item.get("value", "")) for item in entries):
            removed.append(tag)
        else:
            remaining.append(tag)
    return {"deleted_via": deleted_via, "removed": removed,
            "remaining": remaining, "ok": not remaining}


def assertion(name: str, ok: bool, *, evidence: dict | None = None,
              failure: str | None = None) -> dict:
    return {"name": name, "pass": bool(ok), "evidence": evidence or {},
            "failure": failure if not ok else None}


def run() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    started_at = now_z()
    account_a = f"v7-probe-a-{uuid.uuid4().hex[:8]}"
    account_b = f"v7-probe-b-{uuid.uuid4().hex[:8]}"
    device_a = f"mac-a-{uuid.uuid4().hex[:6]}"
    device_b = f"mac-b-{uuid.uuid4().hex[:6]}"

    tag_a_person = probe_tag("A_PERSON")
    tag_a_dnt = probe_tag("A_DNT")
    tag_b_pref = probe_tag("B_PREF")
    used_tags = [tag_a_person, tag_a_dnt, tag_b_pref]

    assertions: list[dict] = []
    try:
        write_memory_scoped(account_a, device_a, kind="person", key="maya",
                            value=f"Maya is my ops partner. {tag_a_person}")
        write_memory_scoped(account_a, device_a, kind="do_not_touch",
                            key="spouse_email",
                            value=f"never email my spouse without confirm. {tag_a_dnt}")
        write_memory_scoped(account_b, device_b, kind="preference",
                            key="coffee",
                            value=f"prefers oat latte. {tag_b_pref}")

        # S1: memory rows expose all required scoping fields.
        entries = list_memory()
        if not entries:
            assertions.append(assertion(
                "S1_memory_entries_have_all_scoping_fields", False,
                failure="GET /api/memory returned no entries at all"))
        else:
            missing_per_entry: list[dict] = []
            for item in entries[:20]:
                missing = [f for f in REQUIRED_FIELDS if f not in item]
                if missing:
                    missing_per_entry.append({"kind": item.get("kind"),
                                              "missing_fields": missing})
            assertions.append(assertion(
                "S1_memory_entries_have_all_scoping_fields",
                not missing_per_entry,
                evidence={
                    "sampled": len(entries[:20]),
                    "required_fields": list(REQUIRED_FIELDS),
                    "first_entry_keys": sorted(entries[0].keys()) if entries else [],
                    "missing_per_entry": missing_per_entry[:5]},
                failure=("At least one memory entry is missing required "
                         "scoping fields") if missing_per_entry else None))

        # S2: account A cannot see account B writes and vice versa.
        a_status, a_body = http_request(
            "GET", f"/api/memory/read?account_id={account_a}&device_id={device_a}")
        b_status, b_body = http_request(
            "GET", f"/api/memory/read?account_id={account_b}&device_id={device_b}")
        if a_status != 200 or b_status != 200:
            assertions.append(assertion(
                "S2_account_isolation", False,
                evidence={"a_status": a_status, "b_status": b_status,
                          "endpoint_present": False},
                failure="/api/memory/read scoped endpoint is not wired"))
        else:
            a_items = a_body.get("items", []) if isinstance(a_body, dict) else []
            b_items = b_body.get("items", []) if isinstance(b_body, dict) else []
            a_text = json.dumps(a_items, default=str)
            b_text = json.dumps(b_items, default=str)
            leaked_into_a = tag_b_pref in a_text
            leaked_into_b = tag_a_person in b_text or tag_a_dnt in b_text
            assertions.append(assertion(
                "S2_account_isolation",
                not leaked_into_a and not leaked_into_b,
                evidence={"a_item_count": len(a_items),
                          "b_item_count": len(b_items),
                          "leaked_into_a": leaked_into_a,
                          "leaked_into_b": leaked_into_b},
                failure=("Account B data leaked into account A read or "
                         "account A data leaked into account B read")
                if (leaked_into_a or leaked_into_b) else None,
            ))

        # S3: pronoun "her" resolves from A's dossier.
        resolve = write_memory_via_inject(account_a, device_a,
                                          "Email her about the meeting")
        body = resolve.get("body") or {}
        resolved_to_maya = "maya" in json.dumps(body, default=str).lower()
        outcome = body.get("outcome") if isinstance(body, dict) else None
        assertions.append(assertion(
            "S3_pronoun_her_resolves_from_account_a_dossier",
            resolved_to_maya,
            evidence={"outcome": outcome, "status": resolve.get("status"),
                      "resolved_substring_check": "maya in body"},
            failure="Engine did not resolve 'her' to Maya for account A"
            if not resolved_to_maya else None))

        # S4: do_not_touch entry blocks the action on the target.
        dnt = write_memory_via_inject(
            account_a, device_a,
            "Email my spouse now and tell them I am running late")
        body = dnt.get("body") or {}
        text = json.dumps(body, default=str).lower()
        blocked = ("decline" in text or "do_not_touch" in text
                   or "competent_decline" in text or "ask" in text)
        assertions.append(assertion(
            "S4_do_not_touch_blocks_action", blocked,
            evidence={"outcome": body.get("outcome")
                      if isinstance(body, dict) else None,
                      "status": dnt.get("status")},
            failure="Engine did not honor do_not_touch on spouse_email"
            if not blocked else None))
    finally:
        cleanup_report = cleanup(used_tags)

    overall_pass = all(item["pass"] for item in assertions)
    verdict = {
        "schema": SCHEMA, "pass": overall_pass,
        "generated_at": started_at, "completed_at": now_z(),
        "engine_url": ENGINE_URL, "assertions": assertions,
        "passed_count": sum(1 for a in assertions if a["pass"]),
        "failed_count": sum(1 for a in assertions if not a["pass"]),
        "cleanup": cleanup_report,
        "frozen_paths_unlocked": ["engine/app/anticipy/memory.py",
                                   "engine/app/product/server.py"],
        "v7_gate_guarded": "V7.20_no_fake_receipts_backdoors_stale_proofs",
        "spec_cite": "ANTICIPY_V7.md PART 0, PART 1A item 4, PART 4, PART 6 item 7",
    }
    OUT_FILE.write_text(json.dumps(verdict, indent=2), encoding="utf-8")
    print(json.dumps(verdict, indent=2))
    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(run())
