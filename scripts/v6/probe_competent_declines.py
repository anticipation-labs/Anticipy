#!/usr/bin/env python3
"""Probe D16 competent declines for unsafe multi-surface writes."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path


CASES = [
    {
        "name": "service now ASR spacing",
        "text": (
            "Update the service now case CASE-414 with the note from Slack "
            "and don't email anyone if you can't prove the record."
        ),
        "intent": "crm_saas_write",
        "blocked_services": ["ServiceNow"],
    },
    {
        "name": "service-now ASR hyphenation",
        "text": (
            "Please add a comment to the service-now ticket INC0042 and "
            "email Jordan when it is done."
        ),
        "intent": "crm_saas_write",
        "blocked_services": ["ServiceNow"],
    },
    {
        "name": "hubspot uploaded-audio follow-up ASR",
        "text": (
            "After my renewal call with Nora Vega at Elder Works, at a "
            "follow-up in HubSpot for Friday morning saying I promised to "
            "send the SOC2 renewal summary, and ask whether finance needs "
            "the vendor packet."
        ),
        "intent": "crm_saas_write",
        "blocked_services": ["HubSpot"],
    },
    {
        "name": "Canva named surface",
        "text": (
            "In Canva, change the client poster headline and email it to "
            "Maya after exporting."
        ),
        "intent": "canvas_edit",
        "blocked_services": ["Canva"],
    },
    {
        "name": "canvas generic ASR surface",
        "text": (
            "Fix the sponsor screen canvas so it says Q4 instead of Q3, "
            "then share it by email."
        ),
        "intent": "canvas_edit",
        "blocked_services": ["canvas"],
    },
]


def _fail(message: str) -> None:
    raise AssertionError(message)


def _latest_receipt(home: Path) -> dict:
    path = home / ".anticipy" / "declined_actions" / "latest.jsonl"
    if not path.exists():
        _fail(f"missing decline receipt at {path}")
    lines = [line for line in path.read_text(encoding="utf-8").splitlines()
             if line.strip()]
    if not lines:
        _fail(f"empty decline receipt at {path}")
    return json.loads(lines[-1])


def _reset_listen(server) -> None:
    with server._LISTEN["lock"]:
        server._LISTEN["windows"] = 0
        server._LISTEN["recent"] = []
        server._LISTEN["pending"] = None
        server._LISTEN["acted"] = None
        server._LISTEN["error"] = None


def _assert_competent_decline(server, home: Path, case: dict) -> None:
    _reset_listen(server)
    rec = server._process_utterance(case["text"], 0.0, "asr-transcript")
    plan = rec.get("plan") or {}
    pending = server._LISTEN.get("pending") or {}

    if rec.get("outcome") != "DECLINED":
        _fail(f"{case['name']}: expected DECLINED, got {rec!r}")
    if rec.get("competent_decline") is not True:
        _fail(f"{case['name']}: returned record is not a competent decline")
    if rec.get("decline") is not True:
        _fail(f"{case['name']}: returned record is missing decline=True")
    if plan.get("mode") != "decline":
        _fail(f"{case['name']}: expected decline plan, got {plan!r}")
    if plan.get("intent") != case["intent"]:
        _fail(f"{case['name']}: expected {case['intent']}, got {plan!r}")
    if not (rec.get("d16_receipt") or plan.get("d16_receipt")):
        _fail(f"{case['name']}: missing D16 receipt marker")
    if pending.get("competent_decline") is not True:
        _fail(f"{case['name']}: pending card is not a competent decline")
    if plan.get("task"):
        _fail(f"{case['name']}: decline must not create a task: {plan!r}")
    if rec.get("scheduled"):
        _fail(f"{case['name']}: decline must not create a scheduled item")

    proposal = str(rec.get("proposal") or "")
    if "Which email address should I use?" in proposal:
        _fail(f"{case['name']}: fell through to generic email clarification")
    if "Open Gmail" in json.dumps(rec, sort_keys=True):
        _fail(f"{case['name']}: created a stray Gmail task")

    receipt = _latest_receipt(home)
    receipt_blob = json.dumps(receipt, sort_keys=True).lower()
    for service in case["blocked_services"]:
        if service.lower() not in receipt_blob:
            _fail(
                f"{case['name']}: receipt does not name {service}: "
                f"{receipt!r}"
            )
    if not receipt.get("d16_receipt"):
        _fail(f"{case['name']}: receipt missing D16 marker: {receipt!r}")
    if not receipt.get("unchanged_state_boundary"):
        _fail(
            f"{case['name']}: receipt missing unchanged-state boundary: "
            f"{receipt!r}"
        )
    if "unchanged" not in receipt_blob:
        _fail(f"{case['name']}: receipt does not preserve unchanged state")
    if "which email address should i use" in receipt_blob:
        _fail(f"{case['name']}: receipt captured generic email clarification")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="anticipy-decline-probe-") as tmp:
        home = Path(tmp)
        os.environ["HOME"] = str(home)
        os.environ["ANTICIPY_ENGINE_PORT"] = str(47000 + os.getpid() % 10000)
        os.environ["ANTICIPY_PORT"] = os.environ["ANTICIPY_ENGINE_PORT"]
        os.environ.pop("ANTICIPY_RESOLUTION_TRACE_SYNC_URL", None)
        os.environ.pop("ANTICIPY_CLOUD_AUTH_TOKEN", None)

        from app.product import server

        server._memory_write = (
            lambda text, kind: {"op": "NOOP", "reason": "probe"}
        )
        for case in CASES:
            _assert_competent_decline(server, home, case)

    print("competent decline probe passed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"competent decline probe failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
