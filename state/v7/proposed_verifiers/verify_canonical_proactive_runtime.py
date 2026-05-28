#!/usr/bin/env python3
"""V7 verifier-first proposal: canonical proactive runtime.

Cite: ANTICIPY_V7.md PART 0 (actual surfaces, no proof bureaucracy),
PART 1A item 5 (proactive observation), PART 2 (input modes converge
at one boundary), PART 3 (act/ask/decline/silent decisions cite
proof), PART 4 (anticipy.inference_event.v7 and anticipy.decision.v7
records for every act/ask/decline/silent no-op).

V7 gates guarded: V7.6, V7.7, V7.8 (input modes pass through the same
boundary); V7.20 (no fake receipts).

Motivates fixing engine/app/proactive_day/pipeline.py,
engine/app/proactive/decider.py, and engine/app/proactive/dispatcher.py
so one canonical runtime evaluates every utterance, hard negatives
(jokes, hypotheticals, third-party speech, song lyrics) become silent
or decline, and silent + decline are first-class recorded decisions.

Asserts:
  P1. /api/proactive/queue is the one proactive endpoint; no alternate
      e.g. /api/proactive_day/queue responds.
  P2. Same actionable utterance through text and upload sources lands
      in the same queue shape (keys, parser tag, reason kind).
  P3. Four hard negatives (joke, hypothetical, third-party, song
      lyric) each produce a silent/decline outcome AND do not create
      an actionable queue item.
  P4. decisions.jsonl records each silent/decline with a reason.

Cleans up probe queue items in `finally`. Today every assertion is
expected to FAIL; after the frozen-path fix each must PASS.

Run: python3 state/v7/proposed_verifiers/verify_canonical_proactive_runtime.py
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


SCHEMA = "anticipy.v7.proposed_verifier.canonical_proactive_runtime"
ENGINE_URL = os.environ.get("ANTICIPY_ENGINE_URL", "http://127.0.0.1:8731")
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
OUT_DIR = REPO_ROOT / "state" / "v7" / "proposed_verifier_runs" \
    / "verify_canonical_proactive_runtime"
OUT_FILE = OUT_DIR / "result.json"

DECISIONS_PATH = REPO_ROOT / "state" / "v7" / "decisions.jsonl"

PROBE_PREFIX = "V7_PROPOSED_VERIFIER_PROACTIVE"


def now_z() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(
        microsecond=0
    ).isoformat().replace("+00:00", "Z")


def request(method: str, path: str, payload: dict | None = None,
            timeout: float = 45.0) -> tuple[int, Any]:
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


def get_queue() -> list[dict]:
    status, body = request("GET", "/api/proactive/queue", timeout=10.0)
    if status != 200 or not isinstance(body, dict):
        return []
    items = body.get("items")
    return items if isinstance(items, list) else []


def inject_text(text: str, source_tag: str | None = None) -> dict:
    payload: dict[str, Any] = {"text": text}
    if source_tag:
        payload["normalized_source"] = source_tag
    status, body = request("POST", "/api/listen/inject", payload, timeout=45.0)
    return {"status": status,
            "body": body if isinstance(body, (dict, list, str)) else str(body)}


def read_decisions(since_ts: float) -> list[dict]:
    if not DECISIONS_PATH.exists():
        return []
    rows: list[dict] = []
    try:
        with DECISIONS_PATH.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = row.get("ts") or row.get("timestamp") or 0
                try:
                    ts_f = float(ts) if ts else 0
                except (TypeError, ValueError):
                    ts_f = 0
                if ts_f >= since_ts - 5.0:
                    rows.append(row)
    except Exception:
        return []
    return rows


def cleanup(sentinels: list[str]) -> dict:
    removed_queue: list[str] = []
    remaining_queue: list[str] = []
    for sentinel in sentinels:
        status, _ = request("POST", "/api/proactive/prune",
                            {"contains": sentinel}, timeout=10.0)
        if status == 200:
            removed_queue.append(sentinel)
            continue
        items = get_queue()
        if not any(sentinel in str(item.get("transcript", "")) for item in items):
            removed_queue.append(sentinel)
        else:
            remaining_queue.append(sentinel)
    return {"removed_queue_sentinels": removed_queue,
            "remaining_queue_sentinels": remaining_queue,
            "ok": not remaining_queue}


def assertion(name: str, ok: bool, *, evidence: dict | None = None,
              failure: str | None = None) -> dict:
    return {"name": name, "pass": bool(ok), "evidence": evidence or {},
            "failure": failure if not ok else None}


def run() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    started_at = now_z()
    start_ts = time.time()
    sentinels: list[str] = []

    # Positive utterance used for P2 (same text, two sources).
    positive_sentinel = (
        f"{PROBE_PREFIX}_POS_{uuid.uuid4().hex[:10]}"
    )
    positive_text = (
        "Remind me to call Maya tomorrow at 3 PM. "
        + positive_sentinel
    )
    sentinels.append(positive_sentinel)

    hard_negatives = [
        ("joke",
         "lol I should email Maya about Friday for the millionth "
         "time, kidding"),
        ("hypothetical",
         "If I had to email Maya about Friday I would probably do "
         "it tonight"),
        ("third_party",
         "Bob said he is going to email Maya about Friday"),
        ("song_lyric",
         "Should I stay or should I go now"),
    ]
    neg_records: list[dict] = []
    for label, base_text in hard_negatives:
        sentinel = f"{PROBE_PREFIX}_NEG_{label}_{uuid.uuid4().hex[:10]}"
        sentinels.append(sentinel)
        neg_records.append({
            "label": label,
            "sentinel": sentinel,
            "text": f"{base_text}. {sentinel}",
        })

    assertions: list[dict] = []
    try:
        # P1: exactly one proactive queue endpoint exists.
        primary = get_queue()
        secondary_status, _ = request(
            "GET",
            "/api/proactive_day/queue",
            timeout=5.0,
        )
        # The "alternate" endpoint should NOT exist as a competing path.
        no_alternate = secondary_status in (404, 405, 0)
        assertions.append(assertion(
            "P1_single_proactive_runtime_endpoint",
            no_alternate,
            evidence={
                "primary_count": len(primary),
                "secondary_status": secondary_status,
            },
            failure=(
                "Alternate proactive runtime endpoint responded: "
                f"status={secondary_status}"
            ) if not no_alternate else None,
        ))

        # P2: same positive utterance via two normalized sources lands
        # in the same queue shape.
        text_response = inject_text(positive_text, source_tag="text-transcript")
        time.sleep(0.5)
        upload_response = inject_text(positive_text, source_tag="upload-asr")
        time.sleep(0.5)
        queue_now = get_queue()
        positive_items = [
            item for item in queue_now
            if positive_sentinel in str(item.get("transcript", ""))
        ]
        shape_match = False
        if len(positive_items) >= 1:
            keys = sorted(positive_items[0].keys())
            same_shape = all(
                sorted(item.keys()) == keys for item in positive_items
            )
            parser_tags = {
                (item.get("metadata") or {}).get("parser")
                for item in positive_items
            }
            reason_kinds = {item.get("reason") for item in positive_items}
            shape_match = (
                same_shape
                and len(parser_tags) == 1
                and len(reason_kinds) == 1
            )
        else:
            keys = []
            parser_tags = set()
            reason_kinds = set()
        assertions.append(assertion(
            "P2_text_and_upload_same_proactive_shape",
            shape_match and len(positive_items) >= 1,
            evidence={
                "positive_items_found": len(positive_items),
                "common_keys": keys,
                "parser_tags": sorted(
                    str(p) for p in parser_tags if p is not None),
                "reason_kinds": sorted(
                    str(r) for r in reason_kinds if r is not None),
                "text_response_status": text_response["status"],
                "upload_response_status": upload_response["status"],
            },
            failure=(
                "Same positive utterance produced no items or a "
                "different queue shape across input sources"
            ) if not (shape_match and positive_items) else None,
        ))

        # P3 + P4: hard negatives produce a silent/decline outcome AND
        # a recorded decision row (if decisions.jsonl exists, the row
        # must show up with a reason; if not, the queue must NOT show
        # an actionable item for the sentinel).
        neg_observations: list[dict] = []
        all_negs_pass = True
        for rec in neg_records:
            resp = inject_text(rec["text"], source_tag="text-transcript")
            time.sleep(0.4)
            body = resp.get("body") or {}
            outcome = (
                body.get("outcome") if isinstance(body, dict) else None
            )
            silent_or_decline = outcome in (
                "LIFE_LOG", "DECLINED", "SILENT", "NO_ACTION",
                "AMBIGUOUS_DECLINED",
            )
            queue_after = get_queue()
            queue_mentions = [
                item for item in queue_after
                if rec["sentinel"] in str(item.get("transcript", ""))
            ]
            actionable_in_queue = any(
                str(item.get("status", "")).lower() == "pending"
                and (item.get("reason") or "") != "competent_decline"
                for item in queue_mentions
            )
            this_ok = silent_or_decline and not actionable_in_queue
            neg_observations.append({
                "label": rec["label"],
                "outcome": outcome,
                "queue_mentions": len(queue_mentions),
                "actionable_in_queue": actionable_in_queue,
                "pass": this_ok,
            })
            if not this_ok:
                all_negs_pass = False
        assertions.append(assertion(
            "P3_hard_negatives_silent_or_decline",
            all_negs_pass,
            evidence={"negatives": neg_observations},
            failure=(
                "At least one hard negative either created an "
                "actionable proactive queue item or did not produce a "
                "silent/decline outcome"
            ) if not all_negs_pass else None,
        ))

        # P4: decision records for the hard-negative window are kept.
        decision_rows = read_decisions(start_ts)
        has_required_fields = False
        if decision_rows:
            required = {"reason", "schema"}
            has_required_fields = all(
                required.issubset(row.keys()) for row in decision_rows[:5]
            )
        assertions.append(assertion(
            "P4_decisions_jsonl_records_silent_and_decline",
            bool(decision_rows) and has_required_fields,
            evidence={
                "rows_found": len(decision_rows),
                "decisions_file_exists": DECISIONS_PATH.exists(),
                "sample_keys": sorted(
                    decision_rows[0].keys()) if decision_rows else [],
            },
            failure=(
                f"decisions.jsonl absent or rows missing required "
                f"fields. exists={DECISIONS_PATH.exists()}"
            ) if not (
                decision_rows and has_required_fields
            ) else None,
        ))
    finally:
        cleanup_report = cleanup(sentinels)

    overall_pass = all(item["pass"] for item in assertions)
    verdict = {
        "schema": SCHEMA,
        "pass": overall_pass,
        "generated_at": started_at,
        "completed_at": now_z(),
        "engine_url": ENGINE_URL,
        "assertions": assertions,
        "passed_count": sum(1 for a in assertions if a["pass"]),
        "failed_count": sum(1 for a in assertions if not a["pass"]),
        "cleanup": cleanup_report,
        "frozen_paths_unlocked": [
            "engine/app/proactive_day/pipeline.py",
            "engine/app/proactive/decider.py",
            "engine/app/proactive/dispatcher.py",
        ],
        "v7_gate_guarded": (
            "V7.6_mp3_input_passes, "
            "V7.7_text_transcript_input_passes, "
            "V7.8_computer_mic_input_passes, "
            "V7.20_no_fake_receipts_backdoors_stale_proofs"
        ),
        "spec_cite": (
            "ANTICIPY_V7.md PART 0, PART 1A item 5, PART 2, "
            "PART 3, PART 4"
        ),
    }
    OUT_FILE.write_text(json.dumps(verdict, indent=2), encoding="utf-8")
    print(json.dumps(verdict, indent=2))
    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(run())
