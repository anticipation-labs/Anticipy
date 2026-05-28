#!/usr/bin/env python3
"""V7 verifier-first proposal: action dispatcher visible receipt.

Cite: ANTICIPY_V7.md PART 0 (every action needs a fresh
surface-readable proof; no fake receipts), PART 1A item 3 (surface
runtime/action execution with surface proof), PART 3 (decisions cite
proof artifacts a verifier inspects without trusting engine logs),
PART 4 (proofs/ family required), PART 7 R5/R7/R8.

V7 gates guarded: V7.10 (real Chrome, no clone), V7.20 (no fake
receipts).

Motivates fixing engine/app/middle/dispatcher.py,
engine/app/proactive/dispatcher.py, and the action call sites in
engine/app/product/server.py (_try_direct_browser_action) so that:

  (a) every browser action returns success only when at least one
      visible receipt is present (DOM, screenshot, AX, file diff, or
      non-empty surface_receipt.proof block);
  (b) a single shared dispatcher mediates browser actions instead of
      two parallel dispatchers racing;
  (c) provider callbacks alone (Chrome JSON tab list, native bridge
      ack-only) do not satisfy visual-task success.

Asserts:
  D1. Visual browser action ran=True/SUCCESS requires a visible
      receipt artifact (file on disk or non-empty proof block).
  D2. Only one Dispatcher class is reachable in the engine source.
  D3. Empty surface_receipt.proof + no receipt file invalidates
      ran=True.
  D4. Second identical action does not double-fire via a competing
      dispatcher path.

Tabs opened during the run are closed in `finally` via /api/act using
the probe sentinel. Today every assertion is expected to FAIL; after
the frozen-path fix each must PASS.

Run: python3 state/v7/proposed_verifiers/verify_action_dispatcher_visible_receipt.py
Verdict at state/v7/proposed_verifier_runs/<name>/result.json.
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


SCHEMA = "anticipy.v7.proposed_verifier.action_dispatcher_visible_receipt"
ENGINE_URL = os.environ.get("ANTICIPY_ENGINE_URL", "http://127.0.0.1:8731")
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
OUT_DIR = REPO_ROOT / "state" / "v7" / "proposed_verifier_runs" \
    / "verify_action_dispatcher_visible_receipt"
OUT_FILE = OUT_DIR / "result.json"

VISIBLE_RECEIPT_KEYS = (
    "screenshot_path",
    "dom_path",
    "ax_dump_path",
    "file_diff_path",
    "page_metadata_path",
    "visible_state_path",
)
SURFACE_PROOF_SUBKEYS = ("dom", "screenshot", "visible_state",
                          "screenshot_path", "dom_path",
                          "page_metadata_path")

DISPATCHER_FILES = (
    REPO_ROOT / "engine" / "app" / "middle" / "dispatcher.py",
    REPO_ROOT / "engine" / "app" / "proactive" / "dispatcher.py",
)


def now_z() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(
        microsecond=0
    ).isoformat().replace("+00:00", "Z")


def request(
    method: str,
    path: str,
    payload: dict | None = None,
    timeout: float = 60.0,
) -> tuple[int, Any]:
    url = ENGINE_URL.rstrip("/") + path
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        url, data=data, headers=headers, method=method
    )
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


def file_exists_and_nonempty(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        path = Path(value)
        if not path.is_absolute():
            path = REPO_ROOT / value
        return path.exists() and path.stat().st_size > 0
    except Exception:
        return False


def has_visible_receipt(act_body: Any) -> tuple[bool, dict]:
    """Return (ok, details) describing whether the response body has
    at least one visible receipt that points to a real artifact on
    disk OR a non-empty proof block inside surface_receipt.proof.
    """
    if not isinstance(act_body, dict):
        return False, {"reason": "body_not_dict"}
    found: dict = {}
    for key in VISIBLE_RECEIPT_KEYS:
        value = act_body.get(key)
        if isinstance(value, str) and value:
            found[key] = {
                "value": value,
                "exists_on_disk": file_exists_and_nonempty(value),
            }
    surface_receipt = act_body.get("surface_receipt")
    if isinstance(surface_receipt, dict):
        proof = surface_receipt.get("proof")
        if isinstance(proof, dict):
            proof_block: dict = {}
            for subkey in SURFACE_PROOF_SUBKEYS:
                if subkey in proof and proof[subkey]:
                    proof_block[subkey] = proof[subkey]
            if proof_block:
                found["surface_receipt.proof"] = proof_block
    ok_any_on_disk = any(
        isinstance(v, dict) and v.get("exists_on_disk") is True
        for v in found.values()
    )
    ok_proof_block = "surface_receipt.proof" in found
    return (ok_any_on_disk or ok_proof_block), {
        "found_keys": sorted(found.keys()),
        "details": found,
    }


def cleanup_tabs(sentinel: str) -> dict:
    """Best-effort: ask the engine to close tabs whose URL/title
    matches the probe sentinel.
    """
    status, body = request(
        "POST",
        "/api/act",
        {"instruction": f"close browser tabs about {sentinel}"},
        timeout=30.0,
    )
    return {"status": status, "body": body}


def assertion(
    name: str,
    ok: bool,
    *,
    evidence: dict | None = None,
    failure: str | None = None,
) -> dict:
    return {
        "name": name,
        "pass": bool(ok),
        "evidence": evidence or {},
        "failure": failure if not ok else None,
    }


def run() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    started_at = now_z()
    sentinel = f"v7probe{uuid.uuid4().hex[:10]}"
    assertions: list[dict] = []
    try:
        # Reset pending to give us a clean engine state.
        request("POST", "/api/listen/reset", {}, timeout=10.0)

        # D1: a visual browser task must carry a visible receipt to
        # be marked ran=True.
        instruction = (
            f"open a google search tab for {sentinel} v7 verifier "
            "probe d1"
        )
        d1_status, d1_body = request(
            "POST",
            "/api/act",
            {"instruction": instruction},
            timeout=60.0,
        )
        d1_ran = (
            isinstance(d1_body, dict)
            and d1_body.get("ran") is True
            and (
                d1_body.get("status") == "SUCCESS"
                or d1_body.get("succeeded") is True
            )
        )
        d1_has_receipt, d1_receipt_details = has_visible_receipt(d1_body)
        d1_pass = True
        if d1_ran and not d1_has_receipt:
            d1_pass = False
        assertions.append(assertion(
            "D1_browser_action_success_requires_visible_receipt",
            d1_pass,
            evidence={
                "status": d1_status,
                "ran": (
                    d1_body.get("ran")
                    if isinstance(d1_body, dict) else None
                ),
                "engine_status": (
                    d1_body.get("status")
                    if isinstance(d1_body, dict) else None
                ),
                "path": (
                    d1_body.get("path")
                    if isinstance(d1_body, dict) else None
                ),
                "receipt_details": d1_receipt_details,
            },
            failure=(
                "Browser action returned ran=True but no visible "
                "receipt artifact on disk and no non-empty "
                "surface_receipt.proof block."
            ) if not d1_pass else None,
        ))

        # D2: only one shared dispatcher module should be reachable.
        # Today two files define class Dispatcher; flag as fail until
        # they are unified or one explicitly delegates to the other.
        present_files = [str(p) for p in DISPATCHER_FILES if p.exists()]
        defines_dispatcher = []
        for p in DISPATCHER_FILES:
            if p.exists():
                try:
                    body = p.read_text(encoding="utf-8")
                    if "class Dispatcher" in body:
                        defines_dispatcher.append(str(p))
                except Exception:
                    pass
        d2_pass = len(defines_dispatcher) <= 1
        assertions.append(assertion(
            "D2_single_shared_dispatcher",
            d2_pass,
            evidence={
                "files_present": present_files,
                "files_defining_class_Dispatcher": defines_dispatcher,
            },
            failure=(
                "More than one Dispatcher class is defined in the "
                "engine. Unify into a single shared dispatcher."
            ) if not d2_pass else None,
        ))

        # D3: provider callback alone does NOT count.
        # We re-read the D1 response and assert: if surface_receipt
        # exists but its proof block is empty, ran=True must NOT be
        # true. (Native messaging often returns ack with proof={}.)
        if isinstance(d1_body, dict):
            sr = d1_body.get("surface_receipt") or {}
            proof = sr.get("proof") if isinstance(sr, dict) else {}
            proof_empty = not isinstance(proof, dict) or not proof
            ran_true = d1_body.get("ran") is True
        else:
            proof_empty = True
            ran_true = False
        d3_pass = not (proof_empty and ran_true and not d1_has_receipt)
        assertions.append(assertion(
            "D3_provider_callback_alone_not_success",
            d3_pass,
            evidence={
                "ran_true": ran_true,
                "surface_receipt_proof_empty": proof_empty,
                "any_visible_receipt": d1_has_receipt,
            },
            failure=(
                "ran=True returned for a visual task with empty "
                "surface_receipt.proof and no visible receipt files."
            ) if not d3_pass else None,
        ))

        # D4: second identical action does not double-fire via a
        # competing dispatcher path.
        time.sleep(0.5)
        d4_status, d4_body = request(
            "POST",
            "/api/act",
            {"instruction": instruction},
            timeout=60.0,
        )
        d4_ran = (
            isinstance(d4_body, dict)
            and d4_body.get("ran") is True
            and (
                d4_body.get("status") == "SUCCESS"
                or d4_body.get("succeeded") is True
            )
        )
        # The shared dispatcher must either dedup (ran=False with a
        # duplicate reason) OR succeed with a fresh visible receipt
        # that is different from D1's. Two unconditional SUCCESS rows
        # with no dedup or differing receipts is the failure mode.
        d4_has_receipt, d4_receipt_details = has_visible_receipt(d4_body)
        d4_pass = (
            (not d4_ran)
            or (
                d4_has_receipt
                and d4_receipt_details.get("found_keys")
                != d1_receipt_details.get("found_keys")
            )
        )
        assertions.append(assertion(
            "D4_no_double_fire_via_competing_dispatcher",
            d4_pass,
            evidence={
                "second_call_status": d4_status,
                "second_ran": (
                    d4_body.get("ran")
                    if isinstance(d4_body, dict) else None
                ),
                "second_receipt_details": d4_receipt_details,
                "first_receipt_keys": d1_receipt_details.get("found_keys"),
            },
            failure=(
                "Second identical /api/act fired ran=True without a "
                "fresh visible receipt; competing dispatcher detected."
            ) if not d4_pass else None,
        ))
    finally:
        cleanup_report = cleanup_tabs(sentinel)

    overall_pass = all(item["pass"] for item in assertions)
    verdict = {
        "schema": SCHEMA,
        "pass": overall_pass,
        "generated_at": started_at,
        "completed_at": now_z(),
        "engine_url": ENGINE_URL,
        "sentinel": sentinel,
        "assertions": assertions,
        "passed_count": sum(1 for a in assertions if a["pass"]),
        "failed_count": sum(1 for a in assertions if not a["pass"]),
        "cleanup": cleanup_report,
        "frozen_paths_unlocked": [
            "engine/app/middle/dispatcher.py",
            "engine/app/proactive/dispatcher.py",
            "engine/app/product/server.py (action call sites)",
        ],
        "v7_gate_guarded": (
            "V7.10_real_chrome_user_surface_no_clone, "
            "V7.20_no_fake_receipts_backdoors_stale_proofs"
        ),
        "spec_cite": (
            "ANTICIPY_V7.md PART 0, PART 1A item 3, PART 3, "
            "PART 4, PART 7 R5/R7/R8"
        ),
    }
    OUT_FILE.write_text(json.dumps(verdict, indent=2), encoding="utf-8")
    print(json.dumps(verdict, indent=2))
    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(run())
