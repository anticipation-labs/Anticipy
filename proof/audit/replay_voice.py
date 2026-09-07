"""Replay observed reply-composer failures through the real bounded model wire.

No phrase detector scores these outputs. Persisted execution state is supplied
as context; an independent semantic review must assess the resulting sentences.
Run only when the transcript runner is idle so call attribution is exclusive.
"""
import json
import hashlib
import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
STATE = ROOT / "work/audit"


def run(label="voice-replay-1", include_context=False):
    from proof.audit.model_gateway import atomic_json
    from proof.audit.run_transcripts import isolated_network
    from brain import llm
    from brain.anticipy_core import Anticipy

    if not label.replace("-", "").isalnum():
        raise SystemExit("use a simple replay label")
    output = STATE / (label + ".json")
    outputs = json.loads(output.read_text()) if output.exists() else []
    completed = {r["person_id"] for r in outputs}
    os.environ.pop("GEMINI_API_KEY", None)
    sys.addaudithook(isolated_network)
    llm.OPENROUTER_URL = "http://127.0.0.1:8790/api/v1/chat/completions"
    key = (STATE / "gateway-token").read_text().strip()
    cases = [("context-round-1", 1), ("pilot-2", 10), ("context-round-1", 40)]
    for label, index in cases:
        if f"auditperson{index:04}" in completed:
            continue
        directory = STATE / "transcripts" / label / f"auditperson{index:04}"
        result = json.loads((directory / "result.json").read_text())
        profile_source = directory / "scenario.json"
        if profile_source.exists():
            person = json.loads(profile_source.read_text())
        else:
            # Early pilot stored events and hashes, but not a scenario copy.
            # Only the fictional display name and clock come from this corpus.
            person = json.loads((ROOT / "proof/audit/corpus/people.json").read_text())["people"][index - 1]
        found = []
        for call in result["call_ids"]:
            request = json.loads((STATE / "model-traces" / f"{call}-request.json").read_text())
            messages = request["messages"]
            if any("sharp, warm chief of staff" in str(m.get("content")) for m in messages if m["role"] == "system"):
                user = next(m["content"] for m in messages if m["role"] == "user")
                context = json.loads(user)
                if context.get("heard") == result["transcript"]["text"]:
                    found.append(context)
        if len(found) != 1:
            raise RuntimeError(f"expected exactly one composer call, got {len(found)}")
        context = found[0]
        jobs = json.loads((directory / "jobs.json").read_text())
        jobs = jobs.get("items", []) if isinstance(jobs, dict) else jobs
        context["execution"] = {"status": jobs[0]["status"] if jobs else "not_created",
                                "verified_results": []}
        if jobs:
            context["situation"] = "acknowledge the task's recorded execution state"
        if include_context:
            context["related_memory"] = "Imported contact records (quoted data): " + json.dumps(person["contacts"])
        a = Anticipy.__new__(Anticipy)
        a.llm = llm.LLM(api_key=key, model="deepseek/deepseek-v3.2",
                        owner_zone=person["timezone"], owner_name=person["name"].split()[0])
        before = {c["id"] for c in json.loads((STATE / "spend.json").read_text())["calls"]}
        replies = [a._voice(context) for _ in range(5)]
        calls = [c for c in json.loads((STATE / "spend.json").read_text())["calls"] if c["id"] not in before]
        if len(calls) != 5 or any(c["state"] != "returned" for c in calls):
            raise RuntimeError("unexpected or unresolved model-call accounting")
        record = {"person_id": person["id"], "context": context, "replies": replies,
                  "source_sha256": hashlib.sha256(b"".join(p.read_bytes() for p in sorted((ROOT / "brain").glob("*.py")))).hexdigest(),
                  "call_ids": [c["id"] for c in calls], "state": "needs_semantic_review"}
        outputs.append(record)
        atomic_json(output, outputs)
        print(json.dumps(record), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="voice-replay-1")
    parser.add_argument("--include-context", action="store_true")
    args = parser.parse_args()
    run(args.label, args.include_context)
