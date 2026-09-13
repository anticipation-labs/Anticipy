"""Read-only, metadata-only preflight for an existing brain fleet upgrade.

This is a point-in-time observation, NOT a drain lock: new work can arrive
after it returns. Never cancel/retry jobs to make this gate green. A first
cutover, changed capacity or incomplete coverage needs a separately reviewed
procedure; a healthy subset of cached workers is not sufficient.

Cloudflare APIs used (no object GET/HEAD or container start/reconcile):
  /workers/scripts/{name}/deployments and /versions/{id} (active bindings)
  /d1/database/{id}/query (fixed SELECT statements only)
  /r2/buckets/{name}/objects (paginated object METADATA, exact-key match)
See https://developers.cloudflare.com/api/resources/r2/subresources/buckets/
subresources/objects/methods/list/ and the Workers Versions / D1 Query docs.
Credentials come only from the existing CI environment, never dotenv or CLI
arguments. Responses/owner IDs remain in memory; output is fixed codes/counts.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import time
import urllib.parse
import urllib.request


ROOT = Path(__file__).resolve().parents[2]
SAFE_ID = re.compile(r"[A-Za-z0-9_-]{8,64}\Z")
UUID = re.compile(r"[A-Fa-f0-9-]{36}\Z")
CF_BASE = "https://api.cloudflare.com/client/v4"
STATUS_URL = "https://api.anticipy.ai/admin/brain/status"
MAX_BODY = 8 * 1024 * 1024
# Predicate is deliberately identical to BrainSupervisor.reconcile(); only
# its projection is narrower. Cursor pagination must not truncate discovery.
DISCOVERY_SQL = """SELECT id FROM owners
WHERE email IS NOT NULL AND email != ''
  AND email NOT LIKE '%.invalid'
  AND email NOT LIKE '%.local'
  AND email NOT LIKE '%@example.%'
  AND id > ? ORDER BY id LIMIT 100"""
RISK_SQL = """SELECT
count(CASE WHEN status='running' OR workflow_state='running' THEN 1 END) AS running,
count(CASE WHEN status NOT IN ('done','failed','cancelled') AND claimed_by!='' THEN 1 END) AS claimed,
count(CASE WHEN status NOT IN ('done','failed','cancelled') AND julianday(lease_until)>julianday('now') THEN 1 END) AS live_leases,
count(CASE WHEN status NOT IN ('done','failed','cancelled') AND effect_uncertain!=0 THEN 1 END) AS uncertain_active,
count(CASE WHEN status IN ('done','failed','cancelled') AND effect_uncertain!=0 THEN 1 END) AS uncertain_terminal,
(SELECT count(*) FROM connection_command_runs WHERE state IS NULL OR state!='completed') AS connector_pending,
(SELECT count(*) FROM purges WHERE memory_purged=0) AS pending_purges,
(SELECT count(*) FROM jobs j
 WHERE j.status='queued' AND j.workflow_state='queued'
   AND typeof(j.workflow_id)='text' AND j.workflow_id!=''
   AND typeof(j.owner_ref)='text' AND j.owner_ref!=''
   AND typeof(j.lease_token)='text' AND j.lease_token!=''
   AND j.lane IS NULL AND typeof(j.attempts) IN ('integer','real') AND j.attempts=0
   AND j.claimed_by IS NULL AND j.lease_until IS NULL AND j.owner IS NULL
   AND (j.effect_uncertain IS NULL OR (typeof(j.effect_uncertain)='integer' AND j.effect_uncertain=0))
   AND NOT EXISTS (SELECT 1 FROM owners o WHERE o.id=j.owner_ref OR o.legacy_uuid=j.owner_ref)
   AND NOT EXISTS (SELECT 1 FROM purges p WHERE p.owner_ref=j.owner_ref)
) AS inactive_unowned_unroutable_invalid,
count(CASE WHEN
  typeof(status)!='text' OR status NOT IN ('awaiting_confirm','queued','running','needs_user','done','failed','cancelled')
  OR typeof(workflow_id)!='text' OR typeof(workflow_state)!='text'
  OR (workflow_state='' AND workflow_id!='')
  OR (workflow_state!='' AND NOT (
       (status='awaiting_confirm' AND workflow_state IN ('draft','awaiting_approval'))
       OR (status='queued' AND workflow_state='queued')
       OR (status='running' AND workflow_state='running')
       OR (status='needs_user' AND workflow_state='needs_user')
       OR (status='done' AND workflow_state='succeeded')
       OR (status='failed' AND workflow_state='failed')
       OR (status='cancelled' AND workflow_state='cancelled')))
  OR typeof(lease_token)!='text' OR typeof(lease_until)!='text' OR typeof(claimed_by)!='text'
  OR (lease_until!='' AND julianday(lease_until) IS NULL)
  OR ((lease_token='') != (lease_until=''))
  OR (lease_token!='' AND (status!='running' OR claimed_by=''))
  OR typeof(effect_uncertain)!='integer' OR effect_uncertain NOT IN (0,1)
  THEN 1 END)
  + (SELECT count(*) FROM purges WHERE typeof(memory_purged)!='integer' OR memory_purged NOT IN (0,1))
  AS invalid_metadata
FROM (
  SELECT status, COALESCE(workflow_id,'') AS workflow_id,
    COALESCE(workflow_state,'') AS workflow_state,
    COALESCE(lease_token,'') AS lease_token,
    COALESCE(lease_until,'') AS lease_until,
    COALESCE(claimed_by,'') AS claimed_by,
    COALESCE(effect_uncertain,0) AS effect_uncertain
  FROM jobs
)"""
# State pairs above mirror workflow_guard.ts STATE_FOR_STATUS / workflow.py
# LEGACY_STATUS. A blank state is admitted only for a genuinely legacy row
# without workflow_id. Unknown structural metadata is not evidence of rest.
# Existing D1 tables can retain nullable legacy columns despite the newer
# CREATE TABLE defaults. Normalize only NULL optional values, matching the
# guard's ?? '' / ?? 0 contract; COALESCE preserves every non-NULL value/type.
# Status and purge completion have no safe empty/false fallback. In particular,
# a retained token with NULL expiry/claimant remains an invalid lease pair.
# The separate inactive category NEVER removes rows from that global count.
# It identifies only unowned, unrouteable legacy rows excluded by the actual
# owner-scoped executor selectors (including legacy aliases), with zero
# recorded attempts and no active execution, explicit uncertainty or purge
# indicated. This is not proof about historical effects. They remain unresolved; the
# release observation is not authorization to adopt, cancel or delete them.


class Refused(Exception):
    """Only fixed program-owned reason codes may be constructed here."""


def require(condition, code):
    if not condition:
        raise Refused(code)


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def count(value):
    return type(value) is int and value >= 0


def check_risk(risk):
    require(isinstance(risk, dict), "risk_metadata_missing")
    fields = ("running", "claimed", "live_leases", "uncertain_active",
              "connector_pending", "pending_purges")
    inactive = "inactive_unowned_unroutable_invalid"
    require(all(count(risk.get(key)) for key in (*fields, "uncertain_terminal", "invalid_metadata", inactive)),
            "risk_metadata_invalid")
    require(risk[inactive] <= risk["invalid_metadata"], "risk_metadata_invalid")
    require(risk["invalid_metadata"] - risk[inactive] == 0, "invalid_work_metadata")
    require(all(risk[key] == 0 for key in fields), "active_or_uncertain_work")


def verify(*, now, cap, configured_cap, live_cap, eligible, fleet, version,
           snapshot_window, snapshots, risk):
    """Pure verdict. Do not return any identifiers, paths or remote prose."""
    require(type(cap) is int and cap == configured_cap == live_cap == 100,
            "capacity_change_requires_review")
    require(finite(now) and finite(snapshot_window) and snapshot_window >= 180,
            "observation_clock_invalid")
    require(isinstance(eligible, list) and eligible and len(set(eligible)) == len(eligible)
            and all(isinstance(owner, str) and SAFE_ID.fullmatch(owner) for owner in eligible),
            "eligible_coverage_invalid")
    require(isinstance(fleet, dict) and fleet.get("ok") is True
            and fleet.get("current") is True and fleet.get("unserved") == []
            and fleet.get("failed") == [] and type(fleet.get("cleanup_failed")) is int
            and fleet["cleanup_failed"] == 0, "fleet_not_ready")
    checked = fleet.get("checked_at")
    require(finite(checked) and 0 <= now - checked / 1000 <= 180, "fleet_observation_stale")
    observation_age = now - checked / 1000
    require(isinstance(fleet.get("version"), dict)
            and fleet["version"].get("id") == version, "fleet_version_mismatch")
    workers = fleet.get("workers")
    require(isinstance(workers, list) and all(isinstance(w, dict) for w in workers),
            "fleet_coverage_invalid")
    observed = [w.get("owner") for w in workers]
    require(len(observed) == len(eligible) and all(isinstance(o, str) for o in observed)
            and len(set(observed)) == len(observed) and set(observed) == set(eligible)
            and type(fleet.get("served")) is int and fleet["served"] == len(eligible),
            "fleet_coverage_mismatch")
    for worker in workers:
        age = worker.get("snapshot_age_seconds")
        require(worker.get("ok") is True and worker.get("child_running") is True
                and worker.get("snapshot_current") is True and worker.get("snapshot_error") is False
                and finite(age) and age >= 0 and age + observation_age <= snapshot_window,
                "worker_snapshot_not_current")
    require(isinstance(snapshots, dict) and set(snapshots) == set(eligible),
            "snapshot_coverage_mismatch")
    for snapshot in snapshots.values():
        require(isinstance(snapshot, dict) and count(snapshot.get("size"))
                and snapshot["size"] > 0 and finite(snapshot.get("modified_at"))
                and 0 <= now - snapshot["modified_at"] <= snapshot_window,
                "r2_snapshot_not_current")
    check_risk(risk)
    return {"ready": True, "scope": "point_in_time_metadata_not_a_drain_lock",
            "covered_owners": len(eligible), "capacity": cap,
            "historical_uncertain_effects": risk["uncertain_terminal"],
            "unresolved_metadata": {
                "invalid_metadata": risk["invalid_metadata"],
                "inactive_unowned_unroutable_invalid": risk["inactive_unowned_unroutable_invalid"],
            },
            "observed_at": datetime.fromtimestamp(now, timezone.utc).isoformat()}


def plan_fleet(discovered, always, cap):
    serve = list(dict.fromkeys(always))
    seen = set(serve)
    unserved = []
    for owner in discovered:
        if owner in seen:
            continue
        if cap <= 0:
            unserved.append(owner)
        else:
            seen.add(owner)
            serve.append(owner)
            cap -= 1
    return serve, unserved


def parse_jsonc(text):
    """Strip structural comments/trailing commas, never characters in strings."""
    out = []
    i = 0
    decoder = json.JSONDecoder()
    while i < len(text):
        if text[i] == '"':
            _, used = decoder.raw_decode(text[i:])
            out.append(text[i:i + used])
            i += used
        elif text.startswith("//", i):
            end = text.find("\n", i)
            i = len(text) if end < 0 else end
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            require(end >= 0, "config_invalid")
            out.append(" ")
            i = end + 2
        else:
            out.append(text[i])
            i += 1
    text = "".join(out)
    out = []
    i = 0
    while i < len(text):
        if text[i] == '"':
            _, used = decoder.raw_decode(text[i:])
            out.append(text[i:i + used])
            i += used
        elif text[i] == "," and text[i + 1:].lstrip().startswith(("}", "]")):
            i += 1
        else:
            out.append(text[i])
            i += 1
    return json.loads("".join(out))


def strict_cap(value):
    require(isinstance(value, str) and re.fullmatch(r"[0-9]+", value) is not None,
            "capacity_invalid")
    return int(value)


def allowlist(value):
    require(isinstance(value, str), "allowlist_metadata_missing")
    values = [part.strip() for part in value.split(",") if part.strip()]
    require(all(SAFE_ID.fullmatch(part) for part in values), "allowlist_metadata_invalid")
    return list(dict.fromkeys(values))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        raise Refused("metadata_redirect_refused")


class MetadataClient:
    def __init__(self, environ):
        self.account = environ.get("CLOUDFLARE_ACCOUNT_ID", "")
        self.token = environ.get("CLOUDFLARE_API_TOKEN", "")
        self.internal_key = environ.get("ANTICIPY_INTERNAL_KEY", "")
        require(re.fullmatch(r"[a-fA-F0-9]{32}", self.account) is not None
                and self.token and self.internal_key, "credentials_unavailable")
        self.opener = urllib.request.build_opener(NoRedirect())

    def request(self, url, *, payload=None, internal=False):
        # Calls below construct only fixed metadata endpoints. No arbitrary URL
        # argument is accepted by the CLI and credentials cannot cross origins.
        parsed = urllib.parse.urlsplit(url)
        require(parsed.scheme == "https" and (url == STATUS_URL if internal else
                parsed.netloc == "api.cloudflare.com" and parsed.path.startswith(
                    f"/client/v4/accounts/{self.account}/")), "metadata_origin_invalid")
        headers = {"Accept": "application/json", "User-Agent": "Anticipy-deploy-preflight/1"}
        headers["X-Internal-Key" if internal else "Authorization"] = (
            self.internal_key if internal else "Bearer " + self.token)
        data = None if payload is None else json.dumps(payload).encode()
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers,
                                         method="GET" if data is None else "POST")
        try:
            with self.opener.open(request, timeout=20) as response:
                require(response.status == 200, "metadata_http_refused")
                raw = response.read(MAX_BODY + 1)
                require(len(raw) <= MAX_BODY, "metadata_response_too_large")
                body = json.loads(raw)
        except Refused:
            raise
        except Exception:
            raise Refused("metadata_request_failed") from None
        require(isinstance(body, dict), "metadata_response_invalid")
        if not internal:
            require(body.get("success") is True, "metadata_api_refused")
        return body

    def cf(self, suffix, *, payload=None):
        return self.request(f"{CF_BASE}/accounts/{self.account}/{suffix}", payload=payload)

    def active(self, name):
        response = self.cf(f"workers/scripts/{name}/deployments")
        deployments = response.get("result", {}).get("deployments")
        require(isinstance(deployments, list) and deployments, "active_deployment_missing")
        require(all(isinstance(d, dict) and isinstance(d.get("created_on"), str)
                    for d in deployments), "active_deployment_invalid")
        latest = max(deployments, key=lambda d: datetime.fromisoformat(d["created_on"].replace("Z", "+00:00")))
        versions = latest.get("versions")
        require(isinstance(versions, list) and len(versions) == 1
                and isinstance(versions[0], dict) and versions[0].get("percentage") == 100,
                "split_deployment_requires_review")
        version = versions[0].get("version_id")
        require(isinstance(version, str) and UUID.fullmatch(version), "active_version_invalid")
        detail = self.cf(f"workers/scripts/{name}/versions/{version}").get("result")
        require(isinstance(detail, dict) and detail.get("id") == version,
                "active_version_mismatch")
        return version, detail.get("resources", {}).get("bindings")

    def query(self, database, sql, params=()):
        # The only write-shaped HTTP request is this fixed SQL SELECT API.
        require(sql in (DISCOVERY_SQL, RISK_SQL) or
                (sql.startswith("SELECT id FROM owners WHERE id IN (")
                 and re.fullmatch(r"SELECT id FROM owners WHERE id IN \([?,]+\) ORDER BY id", sql)),
                "non_read_only_query_refused")
        payload = self.cf(f"d1/database/{database}/query", payload={"sql": sql, "params": list(params)})
        blocks = payload.get("result")
        require(isinstance(blocks, list) and len(blocks) == 1
                and isinstance(blocks[0], dict) and blocks[0].get("success") is True
                and isinstance(blocks[0].get("results"), list), "d1_metadata_invalid")
        meta = blocks[0].get("meta", {})
        require(meta.get("changed_db") is False and type(meta.get("rows_written")) is int
                and meta["rows_written"] == 0, "d1_read_only_unproven")
        return blocks[0]["results"]

    def discover(self, database, always):
        found = []
        cursor = ""
        for _ in range(100):
            rows = self.query(database, DISCOVERY_SQL, [cursor])
            require(len(rows) <= 100 and all(isinstance(row, dict) and isinstance(row.get("id"), str)
                                           for row in rows), "discovery_metadata_invalid")
            ids = [row["id"] for row in rows]
            require(ids == sorted(set(ids)) and all(owner > cursor for owner in ids),
                    "discovery_pagination_invalid")
            found.extend(owner for owner in ids if SAFE_ID.fullmatch(owner))
            if len(rows) < 100:
                break
            cursor = ids[-1]
        else:
            raise Refused("discovery_pagination_incomplete")
        actual = []
        if always:
            marks = ",".join("?" for _ in always)
            rows = self.query(database, f"SELECT id FROM owners WHERE id IN ({marks}) ORDER BY id", always)
            require(all(isinstance(row, dict) and isinstance(row.get("id"), str) for row in rows),
                    "allowlist_coverage_invalid")
            actual = [row["id"] for row in rows]
            require(len(actual) == len(always) and set(actual) == set(always),
                    "allowlist_owner_missing")
        return plan_fleet(found, actual, 100)

    def snapshot(self, bucket, prefix, owner):
        key = f"{prefix}/{owner}/memory.db"
        base = f"r2/buckets/{urllib.parse.quote(bucket, safe='')}/objects"
        cursor = None
        seen = set()
        exact = []
        for _ in range(100):
            params = {"prefix": key, "per_page": "100"}
            if cursor is not None:
                params["cursor"] = cursor
            body = self.cf(base + "?" + urllib.parse.urlencode(params))
            rows, info = body.get("result"), body.get("result_info", {})
            # R2 uses the official CursorPagination contract: result_info is
            # optional and an absent/blank cursor ends pagination. The live
            # terminal response omits result_info entirely. Do not infer an
            # end from page length, and do not ignore explicit contradictions.
            # https://github.com/cloudflare/cloudflare-python/blob/main/src/cloudflare/pagination.py
            # https://github.com/cloudflare/cloudflare-python/blob/main/src/cloudflare/resources/r2/buckets/objects.py
            require(isinstance(rows, list) and isinstance(info, dict), "r2_pagination_invalid")
            if "is_truncated" in info:
                require(type(info["is_truncated"]) is bool, "r2_pagination_invalid")
            next_cursor = info.get("cursor")
            require(next_cursor is None or isinstance(next_cursor, str), "r2_pagination_invalid")
            if info.get("is_truncated") is True:
                require(bool(next_cursor), "r2_pagination_invalid")
            if info.get("is_truncated") is False:
                require(not next_cursor, "r2_pagination_invalid")
            require(all(isinstance(row, dict) and isinstance(row.get("key"), str)
                        and row["key"].startswith(key) for row in rows), "r2_metadata_invalid")
            exact.extend(row for row in rows if row["key"] == key)
            if not next_cursor:
                break
            cursor = next_cursor
            require(isinstance(cursor, str) and cursor and cursor not in seen,
                    "r2_pagination_invalid")
            seen.add(cursor)
        else:
            raise Refused("r2_pagination_incomplete")
        require(len(exact) == 1, "r2_snapshot_missing_or_ambiguous")
        modified = exact[0].get("last_modified")
        require(isinstance(modified, str), "r2_snapshot_timestamp_missing")
        stamp = datetime.fromisoformat(modified.replace("Z", "+00:00"))
        require(stamp.tzinfo is not None, "r2_snapshot_timestamp_invalid")
        return {"size": exact[0].get("size"), "modified_at": stamp.timestamp()}

    def risk(self, database):
        rows = self.query(database, RISK_SQL)
        require(len(rows) == 1, "risk_metadata_invalid")
        check_risk(rows[0])
        return rows[0]

    def fleet(self):
        return self.request(STATUS_URL, internal=True)


def binding(bindings, name, kind):
    require(isinstance(bindings, list), "bindings_unavailable")
    found = [item for item in bindings if isinstance(item, dict) and item.get("name") == name]
    require(len(found) == 1 and found[0].get("type") == kind, "binding_missing_or_ambiguous")
    return found[0]


def run(client, config, cap):
    require(config.get("name") == "anticipy-brain", "deployment_target_invalid")
    variables = config["vars"]
    configured_cap = strict_cap(variables["ANTICIPY_MAX_OWNER_WORKERS"])
    require(cap == configured_cap == 100 and len(config["containers"]) == 1
            and config["containers"][0]["max_instances"] == 100, "capacity_change_requires_review")
    version, bindings = client.active(config["name"])
    live_cap = strict_cap(binding(bindings, "ANTICIPY_MAX_OWNER_WORKERS", "plain_text")["text"])
    require(live_cap == cap, "capacity_change_requires_review")
    always = allowlist(binding(bindings, "ANTICIPY_SERVE_OWNERS", "plain_text")["text"])
    require(set(always) == set(allowlist(variables["ANTICIPY_SERVE_OWNERS"])),
            "allowlist_change_requires_review")
    prefix = binding(bindings, "ANTICIPY_STATE_R2_PREFIX", "plain_text")["text"].strip("/")
    require(prefix == variables["ANTICIPY_STATE_R2_PREFIX"].strip("/") and prefix
            and all(SAFE_ID.fullmatch(part) or re.fullmatch(r"[A-Za-z0-9_-]{1,64}", part)
                    for part in prefix.split("/")), "snapshot_prefix_mismatch")
    interval = strict_cap(binding(bindings, "ANTICIPY_STATE_SNAPSHOT_SECONDS", "plain_text")["text"])
    require(interval == strict_cap(variables["ANTICIPY_STATE_SNAPSHOT_SECONDS"])
            and interval > 0, "snapshot_interval_mismatch")
    configured_db = [b for b in config["d1_databases"] if b.get("binding") == "DB"]
    configured_bucket = [b for b in config["r2_buckets"] if b.get("binding") == "OWNER_STATE"]
    require(len(configured_db) == len(configured_bucket) == 1, "configured_bindings_invalid")
    database = binding(bindings, "DB", "d1").get("id")
    bucket = binding(bindings, "OWNER_STATE", "r2_bucket").get("bucket_name")
    require(isinstance(database, str) and UUID.fullmatch(database)
            and database == configured_db[0]["database_id"], "database_binding_mismatch")
    require(bucket == configured_bucket[0]["bucket_name"] == variables["ANTICIPY_STATE_R2_BUCKET"]
            == binding(bindings, "ANTICIPY_STATE_R2_BUCKET", "plain_text")["text"],
            "snapshot_bucket_mismatch")
    client.risk(database)
    eligible, unserved = client.discover(database, always)
    require(eligible and not unserved, "eligible_fleet_over_capacity_or_empty")
    snapshots = {owner: client.snapshot(bucket, prefix, owner) for owner in eligible}
    fleet = client.fleet()
    # Bracket slow paginated metadata with a second discovery/config/risk read.
    # This detects observed changes; it does not pretend to freeze writers.
    require(client.discover(database, always) == (eligible, unserved), "discovery_changed_during_preflight")
    require(client.active(config["name"]) == (version, bindings), "deployment_changed_during_preflight")
    risk = client.risk(database)
    return verify(now=time.time(), cap=cap, configured_cap=configured_cap, live_cap=live_cap,
                  eligible=eligible, fleet=fleet, version=version,
                  snapshot_window=max(180, interval * 3), snapshots=snapshots, risk=risk)


def main(*, environ=None, client_factory=MetadataClient):
    env = os.environ if environ is None else environ
    try:
        cap = strict_cap(env.get("DEPLOY_CAP", ""))
        config = parse_jsonc((ROOT / "migration/config/wrangler.brain.jsonc").read_text())
        result = run(client_factory(env), config, cap)
    except Refused as error:
        # Refused messages are fixed literals, never raw transport exceptions.
        print(json.dumps({"ready": False, "reason": str(error)}), flush=True)
        return 2
    except Exception:
        print(json.dumps({"ready": False, "reason": "preflight_metadata_unavailable"}), flush=True)
        return 2
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
