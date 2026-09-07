"""Actual job minting + local D1, real model, synthetic connection catalog.

No connected-account credential exists and no execution arm is started.
This proves route selection/persistence without a public-search credential,
not a vendor API effect. The owner fixture is erased in finally.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
from unittest.mock import patch
from urllib.parse import quote

import requests

from brain import llm, hands
from brain.anticipy_core import Anticipy
from brain.memory import Memory
from proof.audit.model_gateway import atomic_json

ROOT = Path(__file__).resolve().parents[2]
BASE = "http://127.0.0.1:8787"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--requires-id", action="store_true")
    args = parser.parse_args()
    path = ROOT / "work/audit" / (args.label + ".json")
    private = path.with_name(args.label + "-private.json")
    if path.exists() or private.exists():
        raise RuntimeError("Use a fresh label")
    session = requests.Session()
    session.trust_env = False
    def request(method, route, **kw):
        response = session.request(method, BASE + route, timeout=30, **kw)
        response.raise_for_status()
        return response.json()
    email = secrets.token_hex(10) + "@anticipy-test.invalid"
    password = secrets.token_urlsafe(32)
    atomic_json(private, {"email":email,"password":password,"base":BASE})
    owner = request("POST", "/api/collections/owners/records", json={
        "email":email,"password":password,"passwordConfirm":password})
    auth = request("POST", "/api/collections/owners/auth-with-password", json={"identity":email,"password":password})
    session.headers["Authorization"] = auth["token"]
    atomic_json(private, {"email":email,"password":password,"base":BASE,"owner_ref":owner["id"],"token":auth["token"]})
    result = {"scope":__doc__, "search_configured":False, "cases":[], "cleaned_up":False,
        "core_source_sha256":hashlib.sha256((ROOT / "brain/anticipy_core.py").read_bytes()).hexdigest()}
    try:
        llm.OPENROUTER_URL = "http://127.0.0.1:8790/api/v1/chat/completions?audit_run=" + quote(args.label)
        model = llm.LLM(api_key=(ROOT / "work/audit/gateway-token").read_text().strip(), model="deepseek/deepseek-v3.2")
        model.gemini_api_key = None
        app = Anticipy(memory=Memory(), llm=model, backend_url=BASE,
                       owner_ref=owner["id"], owner_id=owner["id"])
        catalog = {"document_vault":[{
            "slug":"DOCUMENT_VAULT_SEARCH", "name":"Search workspace documents",
            "description":"Find and read a named document in the connected workspace",
            "toolkit":"document_vault", "tags":["readOnlyHint"],
            "input_parameters":{"type":"object","properties":{"query":{"type":"string"}},"required":["query"]},
        }]}
        if args.requires_id:
            catalog["document_vault"] = [{
                "slug":"DOCUMENT_VAULT_GET", "name":"Read one document by id",
                "description":"Retrieve complete content by its opaque provider-issued document id; cannot search by title",
                "toolkit":"document_vault", "tags":["readOnlyHint"],
                "input_parameters":{"type":"object","properties":{"document_id":{"type":"string",
                    "description":"Opaque document identifier returned by a prior lookup"}},"required":["document_id"]},
            }]
        context = hands.HandContext(connections=(hands.ConnectedApp("document_vault", alias="Orchard workspace"),),
                                    browser_online=False, catalogs=catalog)
        env = dict(os.environ)
        env.pop("BRAVE_API_KEY", None)
        env["ANTICIPY_SERVICE_TOKEN"] = "overnight-local-service-only"
        with patch.dict(os.environ, env, clear=True), patch.object(hands, "gather_context", return_value=context):
            goal = "Read the current Orchard briefing note in the document vault and summarize its delivery dates"
            job_id = app._queue_job(goal, {"source":goal,"now":"2026-09-07 America/Vancouver"}, touches="read", explicit=True)
        if not job_id:
            raise RuntimeError("No task was persisted")
        job = request("GET", "/api/collections/jobs/records/" + job_id)
        note = json.loads(job["params"]).get("_hand", {})
        passed = (job["lane"] == "" and note.get("tool_verdict") == "unclear" if args.requires_id
                  else job["lane"] == "api" and note.get("tool") == "DOCUMENT_VAULT_SEARCH")
        passed = passed and job["owner_ref"] == owner["id"]
        result["requires_opaque_id"] = args.requires_id
        result["cases"].append({"task":goal,"lane":job["lane"],"status":job["status"],"hand":note,"passed":passed})
        print(json.dumps(result["cases"][-1]), flush=True)
    finally:
        cleanup = request("POST", "/me/delete", json={"confirm":"delete"})
        result["cleaned_up"] = cleanup.get("account_deleted") is True
        atomic_json(path, result)
    raise SystemExit(0 if result["cleaned_up"] and all(x["passed"] for x in result["cases"]) else 1)


if __name__ == "__main__":
    main()
