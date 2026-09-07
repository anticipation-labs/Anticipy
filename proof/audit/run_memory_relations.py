"""Real model decisions through the shipped memory store, with isolated data.

Uses the existing loopback audit gateway and its shared spend reservation.
Never connects a provider account, sends a message, or mutates live memory.
"""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import time

from brain import llm
from brain.memory import Memory
from proof.audit.model_gateway import atomic_json

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "work/audit"
CASES = [
    ("separate-people", "Amira manages the Vancouver office and approves the weekly supplier invoices for the local manufacturing and distribution teams", "Simone manages the Vancouver office and approves the weekly supplier invoices for the local manufacturing and distribution teams", "different"),
    ("reversed-roles", "Alex introduced Morgan to Casey", "Morgan introduced Alex to Casey", "different"),
    ("case-sensitive-code", "My access code is AbCd", "My access code is now abcd", "replaces"),
    ("time-correction", "Dinner with Sarah is at 6", "Dinner with Sarah has moved to 8", "replaces"),
    ("denial", "The Devon renewal is signed", "The Devon renewal is not signed", "replaces"),
    ("address-change", "Home is 4 Maple Street", "We moved to Rowan Avenue", "replaces"),
    ("equivalent", "My partner is Sarah", "My partner's name is Sarah", "same"),
    ("new-owner-name", "Their name is Amira and they manage the weekly production schedule for the Vancouver manufacturing and distribution teams", "Their name is Simone and they manage the weekly production schedule for the Vancouver manufacturing and distribution teams", "replaces"),
    ("short-name", "My partner is Jo", "My partner is Al now", "replaces"),
    ("independent-preferences", "I prefer dinner at seven", "I prefer Italian food", "different"),
]

CONTROL_CASES = [
    ("forget-separate-person", "veto", "Amira approves weekly supplier invoices for the Vancouver manufacturing and distribution teams", "Simone approves weekly supplier invoices for the Vancouver manufacturing and distribution teams", False),
    ("forget-paraphrase", "veto", "Marcus Bell is a client and a proposal is in flight", "There is an active proposal for client Marcus Bell", True),
    ("forget-unrelated-project", "veto", "The Atlas project is waiting for the legal team to approve the supplier contract", "The Borealis project is waiting for the legal team to approve the supplier contract", False),
    ("completed-wrong-recipient", "loop", "Send the quarterly project budget update to Morgan and Casey", "I sent the quarterly project budget update to Alex and Casey", False),
    ("completed-paraphrase", "loop", "Send the renewal contract to Priya", "Priya received the renewal agreement I emailed her this morning", True),
    ("planned-is-not-done", "loop", "Send the renewal contract to Priya", "I will send the renewal contract to Priya tomorrow", False),
]


class RecordedLLM(llm.LLM):
    def __init__(self, model_name):
        super().__init__(api_key=(STATE / "gateway-token").read_text().strip(),
                         model=model_name)
        self.gemini_api_key = None
        self.replies = []

    def chat(self, system, user, **kwargs):
        result = super().chat(system, user, **kwargs)
        self.replies.append({"request": json.loads(user), "reply": result.text,
                             "used_model": result.used_model})
        return result


def run(case, model_name):
    key, first, second, expected = case
    model = RecordedLLM(model_name)
    memory = Memory(":memory:", llm=model)
    now = time.time()
    old_id = memory.remember_fact(first, source="interview", ts=now - 86400)
    new_id = memory.remember_fact(second, source="interview", ts=now)
    rows = memory.db.execute("SELECT id, fact, retired_ts FROM profile_facts ORDER BY id").fetchall()
    if expected == "different":
        passed = len(rows) == 2 and all(row[2] is None for row in rows)
    elif expected == "same":
        passed = len(rows) == 1 and old_id == new_id and rows[0][1] == first
    else:
        passed = len(rows) == 2 and rows[0][2] is not None and rows[1][2] is None and rows[1][1] == second
    passed = passed and len(model.replies) == 1
    return {"case": key, "expected": expected, "passed": passed,
            "stored_rows": rows, "calls": model.replies}


def run_control(case, model_name):
    key, kind, first, second, expected = case
    model = RecordedLLM(model_name)
    memory = Memory(":memory:", llm=model)
    if kind == "veto":
        memory.remember_fact(first)
        outcome = memory.forget_fact(second) == 1
        stored = [r["fact"] for r in memory.profile_facts()]
    else:
        memory.db.execute("INSERT INTO nodes(type,name,created_ts,last_seen_ts,status,attrs) VALUES ('commitment',?,1,1,'open','{}')", (first,))
        memory.db.commit()
        outcome = bool(memory.close_from_speech(second, completed=second))
        stored = memory.open_loops()
    return {"case": key, "expected_mutation": expected, "passed": outcome == expected and len(model.replies) == 1,
            "stored": stored, "calls": model.replies}


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--model", default="deepseek/deepseek-v3.2")
    parser.add_argument("--parallel", type=int, default=1)
    args = parser.parse_args()
    destination = STATE / "memory-relations" / args.label / "results.json"
    if destination.exists():
        raise SystemExit("Use a new label; existing evidence is immutable")
    destination.parent.mkdir(parents=True, mode=0o700)
    from urllib.parse import quote
    llm.OPENROUTER_URL = "http://127.0.0.1:8790/api/v1/chat/completions?audit_run=" + quote(args.label, safe="")
    os.environ.pop("ANTICIPY_AUX_MODEL", None)
    with ThreadPoolExecutor(max_workers=args.parallel) as pool:
        results = list(pool.map(lambda case: run(case, args.model), CASES))
        results += list(pool.map(lambda case: run_control(case, args.model), CONTROL_CASES))
    atomic_json(destination, {"scope": "real model; local production memory store; synthetic facts", "results": results})
    for result in results:
        print(result["case"], "PASS" if result["passed"] else "FAIL", flush=True)
    raise SystemExit(0 if all(r["passed"] for r in results) else 1)


if __name__ == "__main__":
    main()
