"""Observe contextual replies on the designated production probe, phone disabled.

This records actual replies for semantic review. It never asserts that receiving
any text proves the right answer, and never exercises a real person's account.
"""
import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from proof.e2e_cloudflare import Api, cancel_job
from proof.audit.model_gateway import atomic_json

ROOT = Path(__file__).resolve().parents[2]
OWNER = "qeuy6sv1raof9rw"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    args = parser.parse_args()
    assert Path(args.label).name == args.label and args.label not in (".", "..")
    output = ROOT / "work/audit" / (args.label + ".json")
    private = output.with_name(args.label + "-private.json")
    if output.exists() or private.exists():
        raise RuntimeError("Preserve previous evidence; choose a fresh label")
    credentials = json.loads((ROOT / "work/audit/secrets.json").read_text())
    api = Api("https://api.anticipy.ai", credentials["ANTICIPY_SERVICE_TOKEN"])
    profiles = api.list("owner_profile", f'owner_ref="{OWNER}"')
    assert len(profiles) == 1
    profile = profiles[0]
    assert profile.get("email", "").endswith(".invalid")
    assert str(profile.get("phone", "")).startswith("+1604555")
    atomic_json(private, {"profile_id": profile["id"], "restore_phone": profile["phone"]})
    budget_path = ROOT / "work/audit/overnight-live-browser-budget.json"
    lock = str(budget_path) + ".lock"
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        budget = json.loads(budget_path.read_text())
        assert budget["reserved_upper_bound_usd"] + 2 <= budget["limit_usd"]
        budget["reserved_upper_bound_usd"] += 2
        budget["calls"].append({"label": args.label, "reserved_usd": 2,
            "at": datetime.now(timezone.utc).isoformat(),
            "purpose": "two contextual replies on the phone-disabled production probe"})
        atomic_json(budget_path, budget)
    finally:
        os.close(fd)
        os.unlink(lock)
    evidence = {"scope": __doc__, "observations": [], "real_messages_sent": 0}
    before = {j["id"] for j in api.list("jobs", f'owner_ref="{OWNER}"')}
    events = []
    try:
        assert api.patch("/api/collections/owner_profile/records/" + profile["id"], {"phone": ""}).ok
        assert not api.record("owner_profile", profile["id"]).get("phone")
        cases = [
            ("ambiguous-contact", "For this isolated test, Avery Chen and Avery Diaz are two different contacts. Neither is preferred and there is no earlier context choosing one. Please draft a message to Avery about reviewing the blue folder. Do not send anything."),
            ("context-answer", "In this isolated example, Morgan promised to send me the red folder, and I promised to review it after it arrives. What did I promise to do? Please answer here; no task or external action is needed."),
        ]
        for name, text in cases:
            # Ordinary conversation replies currently omit parent_line. Use
            # this isolated owner's new rows and retain that attribution limit
            # in evidence instead of inventing a stronger transport contract.
            prior_reply_ids = {r["id"] for r in api.list("events", f'owner_ref="{OWNER}"')}
            response = api.post("/api/collections/events/records", {
                "owner_ref": OWNER, "kind": "app_reply", "source": "typed",
                "device_id": args.label, "text": text, "decision": ""})
            assert response.ok, response.status_code
            event = response.json()
            events.append(event["id"])
            started = time.monotonic()
            replies = []
            while time.monotonic() - started < 240:
                replies = api.list("events", f'owner_ref="{OWNER}" && created>="{event["created"]}"')
                replies = [r for r in replies if r["id"] not in prior_reply_ids
                    and r.get("kind") in ("anticipy_text", "anticipy_says")]
                current = api.record("events", event["id"])
                if replies and current.get("decision") not in (None, "", "processing"):
                    break
                time.sleep(3)
            evidence["observations"].append({"case": name, "source": text,
                "decision": current.get("decision"), "replies": [r.get("text") for r in replies],
                "elapsed_seconds": round(time.monotonic() - started, 2),
                "attribution": "new owner-scoped reply rows during one isolated request; ordinary replies have no parent_line",
                "semantic_review_required": True})
            atomic_json(output, evidence)
            if not replies:
                raise RuntimeError("No persisted reply observed; this is not a passing result")
    finally:
        # Only this isolated run's new jobs are cancelled. Existing probe work
        # and all real-owner records remain outside this script's scope.
        created = [j for j in api.list("jobs", f'owner_ref="{OWNER}"') if j["id"] not in before]
        own_jobs = []
        for job in created:
            params = job.get("params") or {}
            if isinstance(params, str):
                try:
                    params = json.loads(params)
                except ValueError:
                    continue
            if not isinstance(params, dict):
                continue
            source_ids = (params.get("_workflow") or {}).get("source_event_ids") or []
            if any(event in source_ids for event in events):
                own_jobs.append(job)
        evidence["created_jobs"] = [{"status": j.get("status"), "goal": j.get("goal")} for j in own_jobs]
        evidence["tasks_cancelled"] = [cancel_job(api, j, "completed isolated reply proof") for j in own_jobs]
        response = api.patch("/api/collections/owner_profile/records/" + profile["id"], {"phone": profile["phone"]})
        evidence["fixture_phone_restored"] = response.ok and api.record("owner_profile", profile["id"]).get("phone") == profile["phone"]
        atomic_json(output, evidence)
        print(json.dumps(evidence), flush=True)


if __name__ == "__main__":
    main()
