from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from brain import anticipy_core as core
from brain.anticipy_core import Anticipy
from brain.llm import LLM
from brain.memory import Memory


class Response:
    def __init__(self, payload: dict[str, Any], ok: bool = True):
        self.payload, self.ok = payload, ok

    def json(self) -> dict[str, Any]:
        return self.payload

    def raise_for_status(self) -> None:
        if not self.ok:
            raise RuntimeError("in-memory PocketBase request failed")


class PocketBaseRig:
    def __init__(self):
        self.jobs: list[dict[str, Any]] = []

    def get(self, url: str, params: dict | None = None, **_: Any) -> Response:
        if "/jobs/records/" in url:
            job_id = url.rstrip("/").rsplit("/", 1)[-1]
            hit = next((job for job in self.jobs if job["id"] == job_id), None)
            return Response(hit or {}, hit is not None)
        if "/jobs/records" in url:
            filt = (params or {}).get("filter", "")
            states = [
                state for state in ("awaiting_confirm", "queued", "running", "needs_user")
                if state in filt
            ]
            rows = [job for job in self.jobs if not states or job.get("status") in states]
            return Response({"items": list(reversed(rows))})
        return Response({"items": []})

    def post(self, url: str, json: dict | None = None, **_: Any) -> Response:
        if "/jobs/records" not in url:
            return Response({"id": "event"})
        record = dict(json or {})
        record["id"] = f"job-{len(self.jobs) + 1}"
        record.setdefault("created", "now")
        self.jobs.append(record)
        return Response(record)

    def patch(self, url: str, json: dict | None = None, **_: Any) -> Response:
        job_id = url.rstrip("/").rsplit("/", 1)[-1]
        hit = next((job for job in self.jobs if job["id"] == job_id), None)
        if hit is None:
            return Response({}, False)
        hit.update(json or {})
        return Response(hit)


def _norm(value: str) -> str:
    number_words = {
        "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
        "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
        "ten": "10", "eleven": "11", "twelve": "12",
    }
    return " ".join(number_words.get(token, token)
                    for token in re.findall(r"[a-z0-9]+", value.lower()))


def _contains(blob: str, value: str) -> bool:
    expected = _norm(value)
    actual = _norm(blob)
    if not expected:
        return True
    return expected in actual or all(token in actual.split() for token in expected.split())


def run(cases_path: Path, oracle_path: Path, results_path: Path,
        limit: int | None = None, start: int = 0) -> dict[str, Any]:
    cases_doc = json.loads(cases_path.read_text())
    oracle_doc = json.loads(oracle_path.read_text())
    oracles = {item["id"]: item for item in oracle_doc["oracles"]}
    end = None if limit is None else start + limit
    cases = cases_doc["cases"][start:end]
    llm = LLM()
    if not llm.live:
        raise RuntimeError("brain certification requires the live production model")
    rows = []
    for number, case in enumerate(cases, start + 1):
        rig = PocketBaseRig()
        core.pb = rig
        memory = Memory(":memory:", llm=llm)
        anticipy = Anticipy(
            memory=memory, llm=llm, owner_id="certification-owner",
            owner_ref="certification-owner-ref",
        )
        texts: list[str] = []
        anticipy.notify_owner = lambda message, channel="sms": texts.append(message) or {"sent": True}
        history: list[str] = []
        outputs = []
        error = None
        try:
            for turn, utterance in enumerate(case["utterances"], 1):
                output = anticipy.hear(
                    utterance["text"], context=list(history[-8:]),
                    explicit=bool(utterance.get("explicit")),
                    speaker=utterance.get("speaker"),
                    source_event_id=f"{case['id']}-event-{turn}",
                    lineage_key=case["id"],
                )
                history.append(utterance["text"])
                outputs.append({
                    "decision": output["decision"].decision,
                    "goal": output["decision"].goal,
                    "addressee": output["decision"].addressee,
                    "owes": output["decision"].owes,
                    "said": output.get("anticipy_says"),
                })
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"

        oracle = oracles[case["id"]]
        active = [job for job in rig.jobs if job.get("status") in ("awaiting_confirm", "queued", "running", "needs_user")]
        blob = " ".join(
            str(job.get("goal", "")) + " " + str(job.get("params", ""))
            for job in active
        )
        authority_parts = []
        for job in active:
            try:
                job_params = json.loads(job.get("params") or "{}")
            except Exception:
                job_params = {}
            workflow = job_params.get("_workflow") or {}
            authority_parts.extend([
                str(job_params.get("source") or ""),
                str(workflow.get("authority_text") or ""),
                json.dumps(workflow.get("facts") or {}),
            ])
        authority_blob = " ".join(authority_parts)
        answers = " ".join(str(item.get("said") or "") for item in outputs)
        checks = {
            "no_exception": error is None,
            "job_count": len(active) == oracle["expected_jobs"],
            "required_values": all(_contains(blob, value) for value in oracle["required_values"]),
            # Browser execution is gated by exact owner-authored authority,
            # not by a model's goal summary. Detect dropped multi-turn source
            # words before Chrome correctly refuses the resulting plan.
            "authority_grounded": all(
                _contains(authority_blob, value)
                for value in oracle["required_values"]),
            "notification_floor": len(texts) >= oracle["min_notifications"],
            "notification_ceiling": len(texts) <= oracle["max_notifications"],
            "answer_grounded": all(_contains(answers, value) for value in oracle["answer_contains"]),
            "workflow_present": all(bool(job.get("workflow_id")) for job in active),
        }
        passed = all(checks.values())
        job_payloads = []
        for job in active:
            try:
                params = json.loads(job.get("params") or "{}")
            except Exception:
                params = {}
            # This is product output, not oracle data. The browser stage uses
            # only what the brain actually placed on the job.
            job_payloads.append({"goal": job.get("goal", ""), "params": params})
        row = {
            "n": number,
            "id": case["id"],
            "archetype": case["archetype"],
            "domain": case["domain"],
            "passed": passed,
            "checks": checks,
            "job_count": len(active),
            "notifications": len(texts),
            "error": error,
            "decisions": outputs,
            "job_goals": [job.get("goal", "") for job in active],
            "jobs": job_payloads,
            "all_jobs": [
                {"id": job.get("id"), "goal": job.get("goal", ""),
                 "status": job.get("status", ""), "result": job.get("result", "")}
                for job in rig.jobs
            ],
        }
        rows.append(row)
        # Checkpoint each live-model story. A 500-story run lasts long enough
        # for networks and shells to fail; already-observed decisions must not
        # disappear or force an expensive blind restart.
        checkpoint = {
            "candidate": cases_doc["candidate"],
            "seed_hex": cases_doc["seed_hex"],
            "start": start,
            "total": len(rows),
            "passed": sum(item["passed"] for item in rows),
            "failed": sum(not item["passed"] for item in rows),
            "complete": False,
            "rows": rows,
        }
        results_path.parent.mkdir(parents=True, exist_ok=True)
        results_path.write_text(json.dumps(checkpoint, indent=2) + "\n")
        failed = [name for name, ok in checks.items() if not ok]
        print(f"[{number:03d}/{start + len(cases):03d}] {'PASS' if passed else 'FAIL'} {case['archetype']} · {case['domain']}" + (f" · {','.join(failed)}" if failed else ""), flush=True)

    summary = {
        "candidate": cases_doc["candidate"],
        "seed_hex": cases_doc["seed_hex"],
        "start": start,
        "total": len(rows),
        "passed": sum(row["passed"] for row in rows),
        "failed": sum(not row["passed"] for row in rows),
        "complete": True,
        "rows": rows,
    }
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(json.dumps(summary, indent=2) + "\n")
    return summary
