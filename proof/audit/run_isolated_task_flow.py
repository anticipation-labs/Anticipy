"""Input -> real core task formation -> Worker/D1 claim -> server result -> feed.

Fresh phone-less local accounts, no installed browser or external connectors.
Real mode uses only the separately budgeted loopback model gateway. Smoke mode
tests local API/publisher plumbing with an explicit fixture answer, NOT reasoning.
Neither mode seeds a job or overrides task formation, claiming, or verification.
Run under OS outbound-network denial with localhost allowed; the gateway alone
may contact OpenRouter. No production configuration, account or secret is loaded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import tempfile
import time
from urllib.parse import urlencode, urlsplit

import httpx

from proof.audit.model_gateway import atomic_json

ROOT = Path(__file__).resolve().parents[2]
WORKERS = ROOT / "migration/workers"
SCENARIOS = {
    "private-draft": "Anticipy, write a private draft here thanking Avery for reviewing the blue folder. Do not send it to anyone.",
    "supplied-comparison": "Anticipy, prepare a comparison here: North quoted $120 plus $30 delivery; South quoted $140 including delivery. Same items and taxes. Explain the cheaper total. Do not buy anything.",
    "french-draft": "Anticipy, écris ici un brouillon en français pour remercier Camille de son aide hier. Ne l'envoie pas.",
}


def local_gateway(value):
    try:
        url = urlsplit(value)
        valid = (url.scheme == "http" and url.hostname == "127.0.0.1" and url.port
                 and not url.username and not url.password and not url.query and not url.fragment
                 and url.path == "/api/v1/chat/completions")
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("Explicit loopback model gateway required")
    return value


def isolated_environment(token=""):
    # Do not inherit provider credentials, owner defaults, proxies or backend URLs.
    keep = {k: os.environ[k] for k in ("PATH", "HOME", "TMPDIR") if k in os.environ}
    return {**keep, "PYTHON_DOTENV_DISABLED": "1", "CLOUDFLARE_LOAD_DEV_VARS_FROM_DOT_ENV": "false",
            "CLOUDFLARE_INCLUDE_PROCESS_ENV": "false",
            "WRANGLER_SEND_METRICS": "false", "CI": "1", "npm_config_offline": "true",
            "ANTICIPY_SERVICE_TOKEN": "isolated-local-evaluation-only", "OPENROUTER_API_KEY": token,
            "ANTICIPY_STRONG_MODEL": "google/gemini-3.1-pro-preview"}


def verify_task_lineage(params, event_id, result=None, stored_receipt=None):
    """Bind the actual server-work artifact to both stored receipt copies.

    server_work emits a text-sha256 receipt; worker preserves it in the Plan
    and the D1 receipt column. This proves byte/lineage integrity, not meaning.
    Independent semantic review is still required for every real-model case.
    """
    plan = params["_workflow"]
    sources = plan.get("source_event_ids")
    assert (isinstance(sources, list) and sources and all(isinstance(item, str) and item for item in sources)
            and event_id in sources), "input/task lineage missing or malformed"
    receipt = plan.get("receipt") or {}
    evidence = receipt.get("evidence")
    assert (receipt.get("verified") is True and isinstance(evidence, list) and evidence
            and all(isinstance(item, str) and item for item in evidence)), "verified workflow receipt missing or malformed"
    assert isinstance(result, str) and result.strip(), "actual result missing or malformed"
    expected = "text-sha256:" + hashlib.sha256(result.encode("utf-8")).hexdigest()
    assert [item for item in evidence if item.startswith("text-sha256:")] == [expected], "receipt artifact hash does not match actual result"
    # succeed() deliberately strips its summary; server_work hashes its exact
    # result bytes, including any whitespace preserved from public research.
    assert receipt.get("summary") == result.strip(), "receipt summary does not match actual result"
    assert isinstance(stored_receipt, str) and stored_receipt, "stored D1 receipt missing or malformed"
    try:
        mirror = json.loads(stored_receipt)
    except (ValueError, TypeError):
        raise AssertionError("stored D1 receipt missing or malformed") from None
    assert isinstance(mirror, dict) and mirror == receipt, "stored D1 receipt disagrees with workflow receipt"
    server = params.get("_server_work")
    verification = server.get("verification") if isinstance(server, dict) else None
    assert isinstance(verification, dict) and verification.get("verdict") == "satisfied", "server-work verification is not satisfied"


class LocalAPI:
    def __init__(self, directory, port=18555):
        self.directory, self.port = Path(directory), port
        self.base = f"http://127.0.0.1:{port}"
        self.process = None
        self.network = []
        self.log = None

    def __enter__(self):
        try:
            return self._start()
        except BaseException:
            # Context managers do not invoke __exit__ when __enter__ fails.
            # Schema/spawn/readiness failures must still close our own group
            # and log; keep the diagnostic files for review.
            self.__exit__(None, None, None)
            raise

    def _start(self):
        for port in (self.port, self.port + 1):
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", port))
        config = {
            "name": "anticipy-isolated-task-flow", "main": str(WORKERS / "src/index.ts"),
            "compatibility_date": "2026-09-03", "compatibility_flags": ["nodejs_compat"],
            "d1_databases": [{"binding": "DB", "database_name": "isolated-task-flow",
                              "database_id": "00000000-0000-0000-0000-000000000001"}],
            "r2_buckets": [{"binding": "EVIDENCE", "bucket_name": "isolated-evidence"}],
            "durable_objects": {"bindings": [{"name": "PAIR_CODE_COUNTER", "class_name": "PairCodeCounter"}]},
            "migrations": [{"tag": "v1", "new_sqlite_classes": ["PairCodeCounter"]}],
            "assets": {"directory": str(WORKERS / "public"), "binding": "ASSETS"},
            "vars": {"ANTICIPY_ENV": "test", "ANTICIPY_SERVICE_TOKEN": "isolated-local-evaluation-only",
                     "ANTICIPY_AUTH_SECRET": "isolated-auth-not-a-production-secret"},
        }
        self.config = self.directory / "wrangler.json"
        atomic_json(self.config, config)
        self.log = open(self.directory / "workerd.log", "x")
        self.command = ["node", str(WORKERS / "node_modules/wrangler/bin/wrangler.js")]
        self.state = self.directory / "local-state"
        schema_command = [*self.command, "d1", "execute", "DB", "--local", "--config", str(self.config),
                          "--persist-to", str(self.state), "--file", str(ROOT / "migration/d1/schema.sql")]
        self.process = subprocess.Popen(schema_command, cwd=WORKERS, env=isolated_environment(),
                                        stdout=self.log, stderr=self.log, start_new_session=True)
        schema_status = self.process.wait(timeout=40)
        self._stop_process()
        if schema_status != 0:
            raise RuntimeError("Local schema initialization failed; retained local log")
        self.process = subprocess.Popen([*self.command, "dev", "--local", "--config", str(self.config),
                            "--persist-to", str(self.state), "--ip", "127.0.0.1", "--port", str(self.port),
                            "--inspector-port", str(self.port + 1), "--env-file", "/dev/null"],
                            cwd=WORKERS, env=isolated_environment(),
                            stdout=self.log, stderr=self.log, start_new_session=True)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                break
            try:
                if httpx.get(self.base + "/api/health", timeout=1, trust_env=False).status_code == 200:
                    return self
            except httpx.HTTPError:
                pass
            time.sleep(0.2)
        raise RuntimeError("Local Worker did not become ready; retained local log")

    def _stop_process(self):
        if self.process is not None:
            # The group is created by this runner, never discovered by name.
            # Also stop children when the group leader has already exited.
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                self.process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(self.process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                self.process.wait(timeout=5)
            self.process = None

    def __exit__(self, *_):
        try:
            self._stop_process()
        finally:
            if self.log:
                self.log.close()

    def request(self, method, path, body=None, token=None, admin=False):
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("Local API path required")
        headers = {"Authorization": token} if token else {}
        if admin:
            headers["X-Anticipy-Token"] = "isolated-local-evaluation-only"
        with httpx.Client(timeout=15, follow_redirects=False, trust_env=False) as client:
            response = client.request(method, self.base + path, json=body, headers=headers)
        self.network.append({"method": method, "path": path.split("?")[0], "status": response.status_code})
        if response.status_code != 200:
            raise RuntimeError("Local fixture API refused request: " + str(response.status_code))
        return response.json()

    def owned_records(self, collection, owner_id, token):
        # The actual account API requires an explicit owner predicate as well
        # as the account credential. Never use service authority to make this
        # observation pass: the phone must be able to read its own results.
        if collection not in ("jobs", "events") or not isinstance(owner_id, str) or not owner_id or len(owner_id) > 128:
            raise ValueError("A fixture jobs/events collection and owner are required")
        query = urlencode({"filter": "owner_ref=" + json.dumps(owner_id), "perPage": 100})
        page = self.request("GET", f"/api/collections/{collection}/records?{query}", token=token)
        assert isinstance(page, dict) and isinstance(page.get("items"), list), "fixture list response malformed"
        rows = page["items"]
        assert (type(page.get("page")) is int and page["page"] == 1
                and type(page.get("totalPages")) is int and page["totalPages"] in (0, 1)
                and type(page.get("totalItems")) is int and page["totalItems"] == len(rows)
                and len(rows) <= 100), "fixture list observation incomplete"
        assert all(isinstance(row, dict) and row.get("owner_ref") == owner_id for row in rows), "fixture list contains foreign records"
        return rows


def run_case(api, name, smoke=False):
    from brain import llm, worker
    from brain.anticipy_core import Anticipy
    from brain.memory import Memory
    from brain.conversation import Conversation, MockTransport
    from brain.reply_delivery import ReplyDelivery
    email, password = "flow-" + secrets.token_hex(10) + "@anticipy-test.invalid", secrets.token_urlsafe(24)
    owner = api.request("POST", "/api/collections/owners/records", {
        "email": email, "password": password, "passwordConfirm": password})
    auth = api.request("POST", "/api/collections/owners/auth-with-password", {"identity": email, "password": password})
    token = auth["token"]
    result = {"case": name, "passed": False, "scope": "publisher smoke only" if smoke else "core formation, queue, server hand and feed"}
    try:
        api.request("POST", "/me/profile/upsert", {"name": "Casey Fixture", "timezone": "America/Vancouver"}, token)
        event = api.request("POST", "/api/collections/events/records", {
            "owner_ref": owner["id"], "device_id": "isolated-task-flow", "kind": "transcript",
            "source": "typed", "text": SCENARIOS[name], "decision": "", "goal": ""}, token)
        delivery = ReplyDelivery(api.base, owner["id"], MockTransport(), lambda: "")
        worker.PB = api.base
        if smoke:
            answer = delivery.publish(event, "Fixture answer: publisher plumbing only.")
            again = delivery.publish(event, "This duplicate must not replace the original.")
            assert answer["id"] == again["id"] and answer["body"] == again["body"]
            assert api.owned_records("jobs", owner["id"], token) == [], "publisher smoke unexpectedly created a task"
            observed = api.owned_records("events", owner["id"], token)
            assert sum(row["id"] == answer["id"] for row in observed) == 1, "published answer is not readable by its owner"
            result.update(passed=True, input_id=event["id"], reply_id=answer["id"])
        else:
            model = llm.LLM(owner_name="Casey", owner_email=email, owner_zone="America/Vancouver")
            memory = Memory(":memory:", llm=model)
            a = Anticipy(memory=memory, llm=model, owner_ref=owner["id"], backend_url=api.base, owner_phone="")
            convo = Conversation(a, llm=model)
            convo.reply_delivery = delivery.publish
            a.conversation = convo
            # The ordinary core, not a seeded job, decides whether/how to work.
            # This starts at the core's input boundary; app UI and the separate
            # connector-command dispatcher are deliberately outside this case.
            heard = a.hear(SCENARIOS[name], explicit=True, channel="app", capture_source="typed",
                           source_event_id=event["id"], speaker="owner", may_say=lambda *a, **k: False)
            worker.run_research_jobs(a)
            worker.report_finished_jobs(a)
            # Keep only this fresh fixture's validated observations even when
            # a later oracle fails; account cleanup must not erase the evidence
            # needed to distinguish a bad result from a bad test assertion.
            result["observed"] = {"jobs": api.owned_records("jobs", owner["id"], token)}
            result["observed"]["events"] = api.owned_records("events", owner["id"], token)
            jobs, events = result["observed"]["jobs"], result["observed"]["events"]
            completed = [job for job in jobs if job.get("status") == "done"]
            assert len(jobs) == len(completed) == 1, "one newly formed task must complete"
            job = completed[0]
            params = json.loads(job["params"])
            verify_task_lineage(params, event["id"], job.get("result"), job.get("receipt"))
            assert job.get("claimed_by") == worker.RESEARCH_CLAIMANT
            replies = [row for row in events if row.get("external_event_id") == "job-result:" + job["id"]]
            assert len(replies) == 1 and replies[0]["text"] == job["result"]
            # Clear the in-process notification cache to exercise durable dedupe.
            worker.REPORTED.clear()
            worker.report_finished_jobs(a)
            again = api.owned_records("events", owner["id"], token)
            assert len([row for row in again if row.get("external_event_id") == "job-result:" + job["id"]]) == 1
            result.update(passed=True, input_id=event["id"], job_id=job["id"], reply_id=replies[0]["id"],
                          decision=heard["decision"].decision, task=job, semantic_review_required=True)
    except Exception as error:
        result["failure_type"] = type(error).__name__
        # Assertion text is authored by this rig; provider/API bodies are not.
        if isinstance(error, AssertionError):
            result["assertion"] = str(error)
    finally:
        deleted = api.request("POST", "/me/delete", {"confirm": "delete"}, token)
        result["fixture_deleted"] = deleted.get("account_deleted") is True
        result["passed"] = result["passed"] and result["fixture_deleted"]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--state-dir", type=Path)
    parser.add_argument("--gateway-url", type=local_gateway, default="http://127.0.0.1:8794/api/v1/chat/completions")
    parser.add_argument("--cases", nargs="+", choices=SCENARIOS, default=list(SCENARIOS))
    args = parser.parse_args()
    if len(set(args.cases)) != len(args.cases):
        parser.error("Repeated case selection is not allowed")
    token = ""
    if not args.smoke:
        if not args.state_dir:
            parser.error("Real-model mode requires the fresh budgeted gateway state directory")
        token = (args.state_dir / "gateway-token").read_text().strip()
        if not token or len(token) > 4096 or any(not 33 <= ord(char) <= 126 for char in token):
            parser.error("Local gateway token must be a bounded single-line HTTP credential")
    run_dir = Path(tempfile.mkdtemp(prefix="isolated-task-flow-", dir=ROOT / "work"))
    clean_environment = isolated_environment(token)
    os.environ.clear()
    os.environ.update(clean_environment)
    report = {"scope": __doc__, "mode": "smoke" if args.smoke else "real-model", "selected": args.cases,
              "results": [], "paid_calls_in_smoke": 0, "passed": False}
    print(json.dumps({"evidence": str(run_dir / "result.json"), "mode": report["mode"]}), flush=True)
    try:
        from brain import llm
        llm.OPENROUTER_URL = args.gateway_url + "?audit_run=isolated-task-flow"
        with LocalAPI(run_dir) as api:
            os.environ["ANTICIPY_PB"] = api.base
            for name in args.cases:
                result = run_case(api, name, smoke=args.smoke)
                report["results"].append(result)
                report["api_requests"] = api.network
                atomic_json(run_dir / "result.json", report)
                print(json.dumps({"case": name, "passed": result["passed"]}), flush=True)
                if not result["passed"]:
                    break
        report["passed"] = len(report["results"]) == len(args.cases) and all(row["passed"] for row in report["results"])
    except Exception as error:
        report["startup_or_cleanup_failure"] = type(error).__name__
    report["completed"] = len(report["results"])
    report["full_product_verified"] = False
    atomic_json(run_dir / "result.json", report)
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
