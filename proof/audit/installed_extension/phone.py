"""The stand-in phone for the installed-extension proof.

    python3 -m proof.audit.installed_extension.phone owner  --base URL --label NAME
    python3 -m proof.audit.installed_extension.phone pair   --base URL --owner-file F --code 123456
    python3 -m proof.audit.installed_extension.phone unpair --base URL --owner-file F --agent-record ID
    python3 -m proof.audit.installed_extension.phone mint   --base URL --owner-file F --task TEXT --start-url URL
    python3 -m proof.audit.installed_extension.phone job    --base URL --id ID

Every call is the exact HTTP the iPhone app or the brain makes against the
Worker, through the same guards: an owner is created and signed in through
the public owners endpoints; the pair code is looked up and claimed with the
ACCOUNT token (guard.ts rung 5, which is the only caller allowed to set
owner_ref); the job is minted through brain.workflow.new_plan/job_fields so the
row and its embedded plan are wire-exact for workflow_guard. Loopback only.
"""
from __future__ import annotations

import argparse
import json
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))


def call(base: str, method: str, path: str, body=None, token: str = "", agent=None) -> tuple[int, dict]:
    if not base.startswith("http://127.0.0.1"):
        raise SystemExit("loopback only")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = token
    if agent:
        headers["X-Anticipy-Agent-ID"], headers["X-Anticipy-Agent-Token"] = agent
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310 loopback only
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"raw": raw[:300]}


def owner(a) -> int:
    email = f"{a.label}-{secrets.token_hex(4)}@installed-extension.invalid"
    password = secrets.token_urlsafe(18)
    st, rec = call(a.base, "POST", "/api/collections/owners/records",
                   {"email": email, "password": password, "passwordConfirm": password})
    if st != 200:
        print(json.dumps({"step": "create", "status": st, "body": rec}), file=sys.stderr)
        return 1
    st, auth = call(a.base, "POST", "/api/collections/owners/auth-with-password",
                    {"identity": email, "password": password})
    if st != 200 or not auth.get("token"):
        print(json.dumps({"step": "auth", "status": st, "body": auth}), file=sys.stderr)
        return 1
    out = {"id": rec["id"], "email": email, "token": auth["token"]}
    a.owner_file.parent.mkdir(parents=True, exist_ok=True)
    a.owner_file.write_text(json.dumps(out))
    a.owner_file.chmod(0o600)
    print(json.dumps({"id": rec["id"], "email": email}))
    return 0


def load_owner(a) -> dict:
    return json.loads(a.owner_file.read_text())


def pair(a) -> int:
    o = load_owner(a)
    filt = urllib.parse.quote(f'pair_code="{a.code}"')
    st, found = call(a.base, "GET", f"/api/collections/agents/records?filter={filt}&perPage=1", token=o["token"])
    items = found.get("items") or []
    if st != 200 or not items:
        print(json.dumps({"step": "lookup", "status": st, "body": found}), file=sys.stderr)
        return 1
    rec = items[0]
    st, saved = call(a.base, "PATCH", f"/api/collections/agents/records/{rec['id']}",
                     {"owner": o["email"], "owner_ref": o["id"], "paired": True}, token=o["token"])
    if st != 200 or saved.get("paired") is not True:
        print(json.dumps({"step": "claim", "status": st, "body": saved}), file=sys.stderr)
        return 1
    print(json.dumps({"agent_record": rec["id"], "owner_ref": o["id"]}))
    return 0


def unpair(a) -> int:
    """Release the browser the way the app does (AnticipyBackend.swift:703-706):
    `{owner:"", paired:false}` plus `owner_ref:""` when the app holds an account id.
    `--legacy` omits `owner_ref` — the shape an older app, or a release made while
    signed out, produces; the row then stays unpaired with a residual owner_ref."""
    o = load_owner(a)
    body = {"owner": "", "paired": False}
    if not a.legacy:
        body["owner_ref"] = ""
    st, saved = call(a.base, "PATCH", f"/api/collections/agents/records/{a.agent_record}", body, token=o["token"])
    print(json.dumps({"status": st, "paired": saved.get("paired"), "owner_ref_cleared": saved.get("owner_ref", None) == "",
                      "legacy": a.legacy}))
    return 0 if st == 200 else 1


def mint(a) -> int:
    from brain import workflow  # real engine, real wire shape

    o = load_owner(a)
    plan = workflow.new_plan(owner_ref=o["id"], lineage_key=f"installed-ext-{secrets.token_hex(3)}",
                             goal=a.task, consequence=workflow.Consequence.READ_ONLY,
                             source_event_id=f"evt-installed-{secrets.token_hex(3)}")
    params = workflow.put_in_params({"task": a.task, "approved_scope": a.task, "source": "browser",
                                     **({"start_url": a.start_url} if a.start_url else {})}, plan)
    body = {"goal": a.task, "params": json.dumps(params), "device_id": "anticipy", "owner": o["id"],
            "owner_ref": o["id"], "lane": "", **plan.job_fields()}
    # The service principal is the X-Anticipy-Token header (src/index.ts resolvePrincipal rung 0).
    req = urllib.request.Request(a.base + "/api/collections/jobs/records", data=json.dumps(body).encode(),
                                 method="POST", headers={"Content-Type": "application/json",
                                                         "X-Anticipy-Token": a.service_token})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310 loopback only
            st, row = r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        st, row = e.code, {"raw": e.read().decode()[:300]}
    if st != 200:
        print(json.dumps({"step": "mint", "status": st, "body": row}), file=sys.stderr)
        return 1
    print(json.dumps({"job": row["id"], "plan_id": plan.plan_id, "status": row.get("status"),
                      "workflow_state": row.get("workflow_state")}))
    return 0


def job(a) -> int:
    req = urllib.request.Request(f"{a.base}/api/collections/jobs/records/{a.id}",
                                 headers={"X-Anticipy-Token": a.service_token})
    with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310
        row = json.loads(r.read().decode())
    keep = {k: row.get(k) for k in ("id", "status", "workflow_state", "claimed_by", "attempts", "lease_token",
                                    "lease_until", "result", "receipt", "effect_key", "owner_ref")}
    keep["lease_token"] = "set" if keep["lease_token"] else ""
    print(json.dumps(keep))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("command", choices=["owner", "pair", "unpair", "mint", "job"])
    p.add_argument("--base", default="http://127.0.0.1:8791")
    p.add_argument("--label", default="owner")
    p.add_argument("--owner-file", type=Path, default=ROOT / "work/installed-extension/owner.json")
    p.add_argument("--code", default="")
    p.add_argument("--agent-record", default="")
    p.add_argument("--legacy", action="store_true", help="release without clearing owner_ref (older app / signed-out shape)")
    p.add_argument("--task", default="Reveal the slots on the venue page. Read only.")
    p.add_argument("--start-url", default="")
    p.add_argument("--id", default="")
    p.add_argument("--service-token", default="installed-extension-local-only")
    a = p.parse_args(argv)
    # ONE gate for every subcommand, before dispatch. `call()` carried this
    # check, but `mint` and `job` build their own urllib requests for the
    # service-token header and so walked straight past it: a mistyped or
    # copy-pasted --base could have POSTed a job row at the real API. A guard
    # that each new code path has to remember is not a guard.
    if not a.base.startswith("http://127.0.0.1"):
        raise SystemExit(f"loopback only: --base must start with http://127.0.0.1 (got {a.base!r})")
    return {"owner": owner, "pair": pair, "unpair": unpair, "mint": mint, "job": job}[a.command](a)


if __name__ == "__main__":
    sys.exit(main())
