"""Evaluate the current proactive engine against reused Anticipy source cases.

This is the surgical reuse gate for the older "95%" proactive systems. It reads
their JSONL case corpora from separate local checkouts when present, feeds each
case through the live ControlCore owner-ingest path in an isolated temp data dir,
and scores the resulting action cards.

It intentionally does not import old runtime code. Old systems contribute cases;
the live repo owns behavior.

Run a quick representative sample:
  PYTHONPATH=engine engine/.venv/bin/python engine/scripts/proactive_source_truth_eval.py

Run all cases:
  PYTHONPATH=engine PROACTIVE_SOURCE_TRUTH_N=0 engine/.venv/bin/python engine/scripts/proactive_source_truth_eval.py

Run the model-backed canonical decision pipeline:
  PYTHONPATH=engine PROACTIVE_SOURCE_TRUTH_PROVIDER=openrouter PROACTIVE_SOURCE_TRUTH_N=0 engine/.venv/bin/python engine/scripts/proactive_source_truth_eval.py
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

if os.environ.get("PROACTIVE_SOURCE_TRUTH_PROVIDER"):
    os.environ["ANTICIPY_MODEL_PROVIDER"] = os.environ["PROACTIVE_SOURCE_TRUTH_PROVIDER"]
else:
    os.environ.setdefault("ANTICIPY_MODEL_PROVIDER", "stub")
os.environ.setdefault("ANTICIPY_HANDS_MODE", "mock")
os.environ.setdefault("ANTICIPY_NATIVE_BRIDGE_FALLBACK", "0")
os.environ.setdefault("ANTICIPY_TICK_SECONDS", "0")
os.environ.setdefault("ANTICIPY_INBOUND_POLL_SECONDS", "0")

from anticipy_engine.core.control_core import ControlCore  # noqa: E402


CASE_PATHS = [
    Path("/Users/omarebrahim/Developer/Anticipy-V7/engine/data/proactive_e2e.jsonl"),
    Path("/Users/omarebrahim/Developer/Anticipy-V7/engine/data/synth/gold_standard.jsonl"),
    Path("/Users/omarebrahim/Developer/Anticipy-DEV-FINAL/engine/data/proactive_e2e.jsonl"),
    Path("/Users/omarebrahim/Developer/Anticipy-DEV-FINAL/engine/data/synth/gold_standard.jsonl"),
]

BUILTIN_CASES = [
    {
        "name": "builtin_vent_adjacent",
        "difficulty": "medium",
        "transcript": ["Wearer: My brain is fried, call the dentist and book Friday at 3."],
        "expected_intents": ["call the dentist", "book Friday at 3"],
    },
    {
        "name": "builtin_listener_request",
        "difficulty": "medium",
        "transcript": ["Wearer: Hey babe can you grab milk on the way home?"],
        "expected_intents": [],
    },
    {
        "name": "builtin_money_block",
        "difficulty": "medium",
        "transcript": ["Wearer: I need to pay the Xfinity bill today."],
        "expected_intents": ["pay Xfinity bill today"],
    },
]

ADJUDICATION_PATH = Path(
    os.environ.get(
        "PROACTIVE_SOURCE_TRUTH_ADJUDICATIONS",
        "/Users/omarebrahim/Anticipy/engine/data/proactive/source_truth_adjudications.json",
    )
)
FAILURE_LEDGER_PATH = Path(
    os.environ.get(
        "PROACTIVE_SOURCE_TRUTH_FAILURE_LEDGER",
        "/Users/omarebrahim/Anticipy/plan-baby-steps/artifacts/proactive_source_truth_failure_ledger.json",
    )
)

STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "onto", "about",
    "before", "after", "today", "tomorrow", "tonight", "need", "needs", "should",
    "would", "could", "please", "remind", "remember", "make", "sure", "owner",
}


def _row_id(row: dict[str, Any]) -> str:
    name = row.get("name") or row.get("id") or row.get("utterance") or row.get("text") or "unnamed"
    return str(name).strip()[:180]


def _case_key(row: dict[str, Any]) -> str:
    return f"{row.get('_source_path') or 'unknown'}::{_row_id(row)}"


def _load_adjudications() -> dict[str, Any]:
    if not ADJUDICATION_PATH.exists():
        return {"excluded_cases": {}, "notes": "no adjudication manifest present"}
    try:
        data = json.loads(ADJUDICATION_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"excluded_cases": {}, "notes": "adjudication manifest unreadable"}
    return data if isinstance(data, dict) else {"excluded_cases": {}}


def _load_rows() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in CASE_PATHS:
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if not isinstance(row, dict):
                    continue
                if not (row.get("expected_intents") is not None or row.get("expected_label") is not None):
                    continue
                key = f"{path}:{row.get('name') or row.get('id') or row.get('utterance')}"
                if key in seen:
                    continue
                row["_source_path"] = str(path)
                rows.append(row)
                seen.add(key)
    if not rows:
        rows = [{**r, "_source_path": "builtin"} for r in BUILTIN_CASES]
    adjudications = _load_adjudications()
    excluded = adjudications.get("excluded_cases") if isinstance(adjudications.get("excluded_cases"), dict) else {}
    kept = []
    skipped = []
    for row in rows:
        key = _case_key(row)
        if key in excluded or _row_id(row) in excluded:
            skipped.append({"case_key": key, "reason": excluded.get(key) or excluded.get(_row_id(row))})
            continue
        kept.append(row)
    return kept, {"path": str(ADJUDICATION_PATH), "excluded": skipped, "count": len(skipped)}


def _sample(rows: list[dict[str, Any]], n: int) -> list[dict[str, Any]]:
    if n == 0:
        return rows
    by_diff: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_diff.setdefault(str(row.get("difficulty") or "unknown"), []).append(row)
    out: list[dict[str, Any]] = []
    for diff in ("easy", "medium", "hard", "brutal", "unknown"):
        out.extend(by_diff.get(diff, [])[:n])
    return out


def _transcript(row: dict[str, Any]) -> str:
    if isinstance(row.get("transcript"), list):
        return "\n".join(str(x) for x in row["transcript"])
    if row.get("utterance"):
        history = []
        for turn in row.get("turn_history") or []:
            if isinstance(turn, dict):
                speaker = turn.get("speaker") or "Speaker"
                history.append(f"{speaker}: {turn.get('text') or ''}")
        history.append(f"Wearer: {row['utterance']}")
        return "\n".join(history)
    return str(row.get("text") or "")


def _expected(row: dict[str, Any]) -> list[str]:
    label = str(row.get("expected_label") or "").upper()
    if label == "STORE_AS_LATENT" and not row.get("expected_memory_write"):
        return []
    if isinstance(row.get("expected_intents"), list):
        return [str(x) for x in row["expected_intents"] if str(x).strip()]
    if label in {"ACT", "ASK", "STORE", "STORE_AS_LATENT"} and row.get("utterance"):
        return [str(row["utterance"])]
    return []


def _expected_disposition(row: dict[str, Any]) -> str:
    label = str(row.get("expected_label") or "").upper()
    if isinstance(row.get("expected_intents"), list) and row.get("expected_intents"):
        return "act"
    if label in {"ACT", "ASK"}:
        return "act"
    if label == "STORE_AS_LATENT" and not row.get("expected_memory_write"):
        return "ignore"
    if label in {"STORE", "STORE_AS_LATENT"}:
        return "remember"
    if label in {"FOLLOW_UP", "FOLLOWUP"}:
        return "follow_up"
    if label in {"BLOCK", "BLOCKED"}:
        return "block"
    return "ignore"


def _words(text: str) -> set[str]:
    return {
        w for w in re.findall(r"[a-z0-9]+", (text or "").lower())
        if len(w) > 2 and w not in STOPWORDS
    }


def _action_cards(out: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        c for c in (out.get("cards") or [])
        if isinstance(c, dict) and c.get("disposition") in {"do", "ask", "blocked"}
    ]


def _all_cards(out: dict[str, Any]) -> list[dict[str, Any]]:
    return [c for c in (out.get("cards") or []) if isinstance(c, dict)]


def _card_texts(cards: list[dict[str, Any]]) -> list[str]:
    return [
        " ".join(str(c.get(k) or "") for k in ("title", "source_text", "action", "route"))
        for c in cards
    ]


def _covered(expected: str, got_texts: list[str]) -> bool:
    ew = _words(expected)
    if not ew:
        return False
    for got in got_texts:
        gw = _words(got)
        if len(ew & gw) >= max(1, min(2, len(ew))):
            return True
    return False


async def _run_case(core: ControlCore, row: dict[str, Any]) -> dict[str, Any]:
    text = _transcript(row)
    case_key = _case_key(row)
    out = await core.owner_ingest(
        "source_truth_eval",
        text,
        {
            "source_case": _row_id(row),
            "source_case_key": case_key,
            "source_path": row.get("_source_path"),
            "source_of_truth_tags": [
                "ST-SOURCE-TRUTH-EVAL",
                "ST-INFER-REAL-TASKS",
                "ST-IGNORE-VENTS",
                "ST-NO-FAKE-DONE",
            ],
        },
        execute_actions=False,
    )
    exp = _expected(row)
    all_cards = _all_cards(out)
    cards = _action_cards(out)
    got = _card_texts(cards)
    if exp:
        hits = sum(1 for item in exp if _covered(item, got))
        status = "hit" if hits == len(exp) else "partial" if hits else "miss"
    else:
        hits = 0
        status = "correct_ignore" if not cards else "false_fire"
    gateway_event = out.get("gateway_event") if isinstance(out.get("gateway_event"), dict) else {}
    assessment = gateway_event.get("brain_assessment") if isinstance(gateway_event.get("brain_assessment"), dict) else {}
    gateway_failures: list[str] = []
    if all_cards and not gateway_event.get("event_id"):
        gateway_failures.append("missing_gateway_event")
    if all_cards and len(gateway_event.get("possible_tasks") or []) < len(cards):
        gateway_failures.append("gateway_possible_tasks_missing_cards")
    if all_cards and "ST-SOURCE-TRUTH-EVAL" not in (gateway_event.get("source_of_truth_tags") or []):
        gateway_failures.append("missing_source_truth_tag")
    if all_cards and not (assessment.get("evidence") or []):
        gateway_failures.append("missing_brain_assessment_evidence")
    expected_disposition = _expected_disposition(row)
    got_dispositions = sorted({str(c.get("disposition") or "") for c in all_cards if c.get("disposition")})
    wrong_disposition = False
    if expected_disposition == "ignore":
        wrong_disposition = bool(cards)
    elif expected_disposition == "remember":
        wrong_disposition = not any(c.get("disposition") == "remember" for c in all_cards)
    elif expected_disposition == "block":
        wrong_disposition = not any(c.get("disposition") == "blocked" for c in all_cards)
    elif expected_disposition == "act":
        wrong_disposition = not any(c.get("disposition") in {"do", "ask", "blocked"} for c in all_cards)
    return {
        "name": _row_id(row),
        "case_key": case_key,
        "difficulty": row.get("difficulty") or "unknown",
        "source_path": row.get("_source_path"),
        "expected_count": len(exp),
        "expected_disposition": expected_disposition,
        "got_dispositions": got_dispositions,
        "wrong_disposition": wrong_disposition,
        "hit_count": hits,
        "status": status,
        "expected": exp,
        "got": got,
        "card_count": len(cards),
        "gateway_failures": gateway_failures,
        "brain_decisions": out.get("brain_decisions"),
    }


async def _run_case_isolated(row: dict[str, Any], sem: asyncio.Semaphore) -> dict[str, Any]:
    async with sem:
        core = ControlCore(data_dir=Path(tempfile.mkdtemp(prefix="anticipy-source-truth-eval-")))
        await core.start()
        try:
            return await _run_case(core, row)
        finally:
            await core.stop()


async def main() -> int:
    n = int(os.environ.get("PROACTIVE_SOURCE_TRUTH_N", "3"))
    loaded_rows, adjudication_summary = _load_rows()
    rows = _sample(loaded_rows, n)
    provider = os.environ.get("ANTICIPY_MODEL_PROVIDER") or "stub"
    default_concurrency = "2" if provider in {"gemini", "openrouter"} else "1"
    concurrency = max(1, int(os.environ.get("PROACTIVE_SOURCE_TRUTH_CONCURRENCY", default_concurrency)))
    sem = asyncio.Semaphore(concurrency)
    results = await asyncio.gather(*[_run_case_isolated(row, sem) for row in rows])

    totals = {
        "cases": len(results),
        "act_cases": sum(1 for r in results if r["expected_count"]),
        "ignore_cases": sum(1 for r in results if not r["expected_count"]),
        "hit": sum(1 for r in results if r["status"] == "hit"),
        "partial": sum(1 for r in results if r["status"] == "partial"),
        "miss": sum(1 for r in results if r["status"] == "miss"),
        "correct_ignore": sum(1 for r in results if r["status"] == "correct_ignore"),
        "false_fire": sum(1 for r in results if r["status"] == "false_fire"),
        "wrong_disposition": sum(1 for r in results if r.get("wrong_disposition")),
        "gateway_failures": sum(len(r.get("gateway_failures") or []) for r in results),
        "adjudicated_excluded": adjudication_summary["count"],
    }
    act = totals["act_cases"] or 1
    totals["full_coverage_rate"] = round(totals["hit"] / act, 3)
    totals["any_coverage_rate"] = round((totals["hit"] + totals["partial"]) / act, 3)

    print("PROACTIVE SOURCE-TRUTH EVAL")
    print(json.dumps(totals, indent=2, sort_keys=True))
    failures = [r for r in results if (
        r["status"] not in {"hit", "correct_ignore"}
        or r.get("wrong_disposition")
        or r.get("gateway_failures")
    )]
    ledger = {
        "totals": totals,
        "provider": os.environ.get("ANTICIPY_MODEL_PROVIDER"),
        "sample_n": n,
        "concurrency": concurrency,
        "adjudication": adjudication_summary,
        "failures": failures,
    }
    FAILURE_LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    FAILURE_LEDGER_PATH.write_text(json.dumps(ledger, indent=2, sort_keys=True), encoding="utf-8")
    print(f"failure_ledger={FAILURE_LEDGER_PATH}")
    for r in results:
        if (
            r["status"] not in {"hit", "correct_ignore"}
            or r.get("wrong_disposition")
            or r.get("gateway_failures")
        ):
            print(f"[{r['status']}] {r['difficulty']} {r['name']}")
            if r.get("gateway_failures"):
                print(f"  gateway_failures={r['gateway_failures']}")
            if r.get("wrong_disposition"):
                print(f"  disposition expected={r['expected_disposition']} got={r['got_dispositions']}")
            print(f"  expected={r['expected']}")
            print(f"  got={r['got'][:5]}")
    strict = (os.environ.get("PROACTIVE_SOURCE_TRUTH_STRICT", "1") or "").strip().lower() not in {
        "0", "false", "no", "off"
    }
    if strict:
        return 0 if (
            totals["false_fire"] == 0
            and totals["miss"] == 0
            and totals["partial"] == 0
            and totals["wrong_disposition"] == 0
            and totals["gateway_failures"] == 0
        ) else 1
    return 0 if totals["false_fire"] == 0 and totals["any_coverage_rate"] >= 0.75 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
