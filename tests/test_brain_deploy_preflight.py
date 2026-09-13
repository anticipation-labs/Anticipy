"""Release observation must not confuse a healthy subset with full coverage."""
from copy import deepcopy
import importlib
import json
from pathlib import Path
import sqlite3

import pytest


def gate():
    return importlib.import_module("proof.audit.brain_deploy_preflight")


def evidence():
    now = 1_800_000_000.0
    owners = ["owner_AAAA", "owner_BBBB", "probe_CCCC"]
    return {
        "now": now,
        "cap": 100,
        "configured_cap": 100,
        "live_cap": 100,
        "eligible": owners,
        "fleet": {
            "version": {"id": "version-fixture"},
            "checked_at": now * 1000 - 1000,
            "current": True, "ok": True,
            "served": 3, "unserved": [], "failed": [], "cleanup_failed": 0,
            "workers": [{"owner": owner, "ok": True, "child_running": True,
                         "snapshot_current": True, "snapshot_error": False,
                         "snapshot_age_seconds": 2} for owner in owners],
        },
        "version": "version-fixture",
        "snapshot_window": 180,
        "snapshots": {owner: {"size": 4096, "modified_at": now - 3} for owner in owners},
        "risk": {"running": 0, "claimed": 0, "live_leases": 0,
                 "uncertain_active": 0, "uncertain_terminal": 3,
                 "connector_pending": 0, "pending_purges": 0, "invalid_metadata": 0},
    }


def test_healthy_full_fleet_passes_without_echoing_owner_values():
    result = gate().verify(**evidence())
    assert result["ready"] is True
    assert result["covered_owners"] == 3
    assert result["historical_uncertain_effects"] == 3
    assert "owner_" not in json.dumps(result)
    assert "probe_" not in json.dumps(result)


@pytest.mark.parametrize("mutation", [
    lambda e: e["fleet"]["workers"].pop(),
    lambda e: e["fleet"]["workers"].append(deepcopy(e["fleet"]["workers"][0])),
    lambda e: e["fleet"].update(served=2),
    lambda e: e["fleet"].update(checked_at=e["now"] * 1000 - 181000),
    lambda e: e["fleet"].update(checked_at=e["now"] * 1000 + 1000),
    lambda e: e["fleet"].update(unserved=["other_DDDD"]),
    lambda e: e["fleet"].update(cleanup_failed=1),
    lambda e: e["fleet"]["workers"][0].update(snapshot_current=False),
    lambda e: e["fleet"]["workers"][0].update(snapshot_error=True),
    lambda e: e["fleet"]["workers"][0].update(snapshot_age_seconds=180),
    lambda e: e["fleet"]["workers"][0].update(child_running=False),
    lambda e: e["fleet"]["version"].update(id="different-version"),
    lambda e: e["snapshots"].pop("owner_BBBB"),
    lambda e: e["snapshots"]["owner_BBBB"].update(size=0),
    lambda e: e["snapshots"]["owner_BBBB"].update(modified_at=e["now"] - 181),
    lambda e: e["snapshots"]["owner_BBBB"].update(modified_at=e["now"] + 5),
    lambda e: e.update(eligible=[]),
    lambda e: e.update(cap=1),
    lambda e: e.update(live_cap=1),
    lambda e: e.update(configured_cap=1),
])
def test_missing_stale_partial_or_wrong_capacity_evidence_refuses(mutation):
    sample = evidence()
    mutation(sample)
    with pytest.raises(gate().Refused):
        gate().verify(**sample)


@pytest.mark.parametrize("field", ["running", "claimed", "live_leases", "uncertain_active",
                                   "connector_pending", "pending_purges"])
def test_inflight_or_uncertain_work_refuses_without_mutation(field):
    sample = evidence()
    sample["risk"][field] = 1
    with pytest.raises(gate().Refused):
        gate().verify(**sample)


@pytest.mark.parametrize("value", [None, False, -1, "0", float("nan")])
@pytest.mark.parametrize("field", ["running", "invalid_metadata"])
def test_missing_or_coerced_risk_counts_never_mean_zero(value, field):
    sample = evidence()
    sample["risk"][field] = value
    with pytest.raises(gate().Refused):
        gate().verify(**sample)


def test_fleet_plan_matches_always_outside_cap_and_deduplicates():
    assert gate().plan_fleet(["a-owner1", "b-owner2", "c-owner3"],
                            ["probe001", "a-owner1", "probe001"], 1) == (
                                ["probe001", "a-owner1", "b-owner2"], ["c-owner3"])


def test_query_predicate_matches_real_supervisor_and_projects_only_ids():
    module = gate()
    source = (module.ROOT / "migration/workers/brain/src/index.ts").read_text()
    for predicate in ["email IS NOT NULL", "email != ''", "email NOT LIKE '%.invalid'",
                      "email NOT LIKE '%.local'", "email NOT LIKE '%@example.%'"]:
        assert predicate in module.DISCOVERY_SQL
        assert predicate in source
    assert "SELECT id FROM owners" in module.DISCOVERY_SQL
    assert "legacy_uuid" not in module.DISCOVERY_SQL


def test_transport_never_uses_object_get_or_prints_remote_error(capsys):
    module = gate()
    class Broken:
        def __init__(self, *_args, **_kwargs):
            raise RuntimeError("PRIVATE_OWNER secret-value customer-message")
    assert module.main(environ={}, client_factory=Broken) == 2
    output = capsys.readouterr()
    assert "PRIVATE_OWNER" not in output.out + output.err
    assert "secret-value" not in output.out + output.err
    assert json.loads(output.out)["ready"] is False


def test_jsonc_parser_preserves_comment_markers_inside_strings():
    assert gate().parse_jsonc('{// comment\n"url":"https://fixture.invalid/x", /* c */ "a":[1,],}') == {
        "url": "https://fixture.invalid/x", "a": [1]}


def test_workflow_uses_gate_before_deploy_and_preserves_existing_strategy():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/brain-deploy.yml").read_text()
    assert "python3 -m proof.audit.brain_deploy_preflight" in workflow
    assert workflow.index("python3 -m proof.audit.brain_deploy_preflight") < workflow.index("wrangler deploy")
    assert "wrangler r2 object get" not in workflow
    assert 'echo "owner $ref' not in workflow
    assert "--containers-rollout immediate" in workflow
    assert "default: '1'" in workflow
    assert 'ANTICIPY_MAX_OWNER_WORKERS:"$cap"' in workflow


def metadata_client():
    return gate().MetadataClient({"CLOUDFLARE_ACCOUNT_ID": "a" * 32,
                                  "CLOUDFLARE_API_TOKEN": "synthetic-token",
                                  "ANTICIPY_INTERNAL_KEY": "synthetic-internal"})


def test_discovery_reads_all_pages_not_only_first_healthy_workers():
    client = metadata_client()
    requested = []
    first = [{"id": f"owner_{i:04}"} for i in range(100)]
    def query(_db, sql, params):
        requested.append((sql, params))
        if sql == gate().DISCOVERY_SQL:
            return first if params == [""] else [{"id": "owner_0100"}]
        return [{"id": "probe_CCCC"}]
    client.query = query
    served, unserved = client.discover("db", ["probe_CCCC"])
    assert len(served) == 101  # allowlist is outside the discovery cap
    assert unserved == ["owner_0100"]
    assert requested[1] == (gate().DISCOVERY_SQL, ["owner_0099"])


def test_discovery_repeated_page_or_missing_allowlisted_owner_refuses():
    client = metadata_client()
    client.query = lambda *_args: [{"id": f"owner_{i:04}"} for i in range(100)]
    with pytest.raises(gate().Refused, match="discovery_pagination_invalid"):
        client.discover("db", [])
    client.query = lambda *_args: []
    with pytest.raises(gate().Refused, match="allowlist_owner_missing"):
        client.discover("db", ["probe_CCCC"])


def test_r2_uses_paginated_metadata_only_and_matches_exact_key():
    client = metadata_client()
    requested = []
    def cf(path):
        requested.append(path)
        if len(requested) == 1:
            return {"result": [{"key": "owners/owner_AAAA/memory.db.backup"}],
                    "result_info": {"is_truncated": True, "cursor": "second"}}
        return {"result": [{"key": "owners/owner_AAAA/memory.db", "size": 42,
                            "last_modified": "2027-01-15T08:00:00Z"}],
                "result_info": {"is_truncated": False}}
    client.cf = cf
    result = client.snapshot("fixture-bucket", "owners", "owner_AAAA")
    assert result["size"] == 42
    assert len(requested) == 2 and "cursor=second" in requested[1]
    assert all(path.startswith("r2/buckets/fixture-bucket/objects?") for path in requested)
    assert all("/objects/" not in path for path in requested)


@pytest.mark.parametrize("body", [
    {"result": [], "result_info": {}},
    {"result": [], "result_info": {"is_truncated": False}},
    {"result": [], "result_info": {"is_truncated": True}},
    {"result": [{"key": "owners/owner_AAAA/memory.db.old"}],
     "result_info": {"is_truncated": False}},
])
def test_unproven_or_prefix_only_r2_metadata_refuses(body):
    client = metadata_client()
    client.cf = lambda *_args: body
    with pytest.raises(gate().Refused):
        client.snapshot("fixture-bucket", "owners", "owner_AAAA")


def r2_exact_fixture():
    return {"key": "owners/owner_AAAA/memory.db", "size": 4096,
            "last_modified": "2027-01-15T08:00:00Z"}


def test_r2_observed_terminal_response_omits_optional_pagination_metadata():
    """Actual live field schema: success/errors/messages/result, no result_info."""
    client = metadata_client()
    client.cf = lambda *_args: {"success": True, "errors": [], "messages": [],
                               "result": [r2_exact_fixture()]}
    assert client.snapshot("fixture-bucket", "owners", "owner_AAAA")["size"] == 4096


def test_r2_official_cursor_paginator_continues_without_truncated_flag():
    client = metadata_client()
    requested = []
    def cf(path):
        requested.append(path)
        if len(requested) == 1:
            return {"result": [], "result_info": {"cursor": "page-two"}}
        return {"result": [r2_exact_fixture()]}
    client.cf = cf
    assert client.snapshot("fixture-bucket", "owners", "owner_AAAA")["size"] == 4096
    assert len(requested) == 2 and "cursor=page-two" in requested[1]


@pytest.mark.parametrize("info", [{}, {"cursor": ""}, {"cursor": None},
                                  {"is_truncated": False, "cursor": None}])
def test_r2_terminal_optional_blank_or_null_cursor_matches_official_sdk(info):
    client = metadata_client()
    client.cf = lambda *_args: {"result": [r2_exact_fixture()], "result_info": info}
    assert client.snapshot("fixture-bucket", "owners", "owner_AAAA")["size"] == 4096


@pytest.mark.parametrize("info", [
    {"is_truncated": True}, {"is_truncated": True, "cursor": ""},
    {"is_truncated": False, "cursor": "contradictory-next-page"},
    {"is_truncated": "false"}, {"cursor": False}, {"cursor": []},
    None, [],
])
def test_r2_exact_match_cannot_hide_invalid_or_incomplete_pagination(info):
    client = metadata_client()
    client.cf = lambda *_args: {"result": [r2_exact_fixture()], "result_info": info}
    with pytest.raises(gate().Refused, match="r2_pagination_invalid"):
        client.snapshot("fixture-bucket", "owners", "owner_AAAA")


def test_r2_repeated_cursor_refuses_even_after_exact_match():
    client = metadata_client()
    client.cf = lambda *_args: {"result": [r2_exact_fixture()],
                               "result_info": {"cursor": "same-page"}}
    with pytest.raises(gate().Refused, match="r2_pagination_invalid"):
        client.snapshot("fixture-bucket", "owners", "owner_AAAA")


def test_r2_absent_result_info_does_not_turn_missing_object_green():
    client = metadata_client()
    client.cf = lambda *_args: {"result": []}
    with pytest.raises(gate().Refused, match="r2_snapshot_missing_or_ambiguous"):
        client.snapshot("fixture-bucket", "owners", "owner_AAAA")


def test_d1_transport_only_accepts_declared_selects_and_zero_writes():
    client = metadata_client()
    requested = []
    def cf(path, *, payload):
        requested.append((path, payload))
        return {"result": [{"success": True, "results": [{"running": 0}],
                            "meta": {"changed_db": False, "rows_written": 0}}]}
    client.cf = cf
    assert client.query("fixture-db", gate().RISK_SQL) == [{"running": 0}]
    for sql in ["DELETE FROM jobs", "SELECT * FROM owners", "SELECT id FROM owners; DELETE FROM jobs"]:
        with pytest.raises(gate().Refused, match="non_read_only_query_refused"):
            client.query("fixture-db", sql)
    assert len(requested) == 1
    client.cf = lambda *_args, **_kwargs: {"result": [{"success": True, "results": [],
                                                       "meta": {"changed_db": False}}]}
    with pytest.raises(gate().Refused, match="d1_read_only_unproven"):
        client.query("fixture-db", gate().RISK_SQL)


def test_active_version_comes_from_deployment_not_latest_uploaded_version():
    client = metadata_client()
    requested = []
    version = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    def cf(path):
        requested.append(path)
        if path.endswith("/deployments"):
            return {"result": {"deployments": [{"created_on": "2026-09-13T05:00:00Z",
                     "versions": [{"version_id": version, "percentage": 100}]}]}}
        return {"result": {"id": version, "resources": {"bindings": []}}}
    client.cf = cf
    assert client.active("anticipy-brain") == (version, [])
    assert requested == ["workers/scripts/anticipy-brain/deployments",
                         "workers/scripts/anticipy-brain/versions/" + version]


def test_transport_refuses_redirects_and_never_repeats_exception_prose():
    with pytest.raises(gate().Refused, match="metadata_redirect_refused"):
        gate().NoRedirect().redirect_request(None, None, 302, "found", {}, "https://evil.invalid")
    client = metadata_client()
    class BrokenOpener:
        def open(self, *_args, **_kwargs):
            raise RuntimeError("secret-key-and-private-owner")
    client.opener = BrokenOpener()
    with pytest.raises(gate().Refused) as caught:
        client.fleet()
    assert str(caught.value) == "metadata_request_failed"
    with pytest.raises(gate().Refused, match="metadata_origin_invalid"):
        client.request("https://evil.invalid", internal=True)


def run_fixture():
    sample = evidence()
    config = {"name": "anticipy-brain", "containers": [{"max_instances": 100}],
              "vars": {"ANTICIPY_MAX_OWNER_WORKERS": "100", "ANTICIPY_SERVE_OWNERS": "probe_CCCC",
                       "ANTICIPY_STATE_R2_PREFIX": "owners", "ANTICIPY_STATE_SNAPSHOT_SECONDS": "60",
                       "ANTICIPY_STATE_R2_BUCKET": "fixture-bucket"},
              "d1_databases": [{"binding": "DB", "database_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"}],
              "r2_buckets": [{"binding": "OWNER_STATE", "bucket_name": "fixture-bucket"}]}
    bindings = [{"name": key, "type": "plain_text", "text": value} for key, value in config["vars"].items()]
    bindings += [{"name": "DB", "type": "d1", "id": config["d1_databases"][0]["database_id"]},
                 {"name": "OWNER_STATE", "type": "r2_bucket", "bucket_name": "fixture-bucket"}]
    class Client:
        def __init__(self):
            self.calls = []
        def active(self, _name):
            self.calls.append("active")
            return sample["version"], deepcopy(bindings)
        def risk(self, _database):
            self.calls.append("risk")
            return deepcopy(sample["risk"])
        def discover(self, _database, _always):
            self.calls.append("discover")
            return list(sample["eligible"]), []
        def snapshot(self, _bucket, _prefix, owner):
            self.calls.append("snapshot")
            return sample["snapshots"][owner]
        def fleet(self):
            self.calls.append("fleet")
            return deepcopy(sample["fleet"])
    return config, sample, Client()


def test_full_preflight_brackets_snapshots_with_fresh_discovery_settings_and_risk(monkeypatch):
    config, sample, client = run_fixture()
    monkeypatch.setattr(gate().time, "time", lambda: sample["now"])
    assert gate().run(client, config, 100)["ready"] is True
    assert client.calls == ["active", "risk", "discover", "snapshot", "snapshot", "snapshot",
                            "fleet", "discover", "active", "risk"]


def test_owner_appearing_after_snapshot_read_refuses(monkeypatch):
    config, sample, client = run_fixture()
    original = client.discover
    def discover(*args):
        rows, _ = original(*args)
        return rows + (["new_owner"] if client.calls.count("discover") > 1 else []), []
    client.discover = discover
    monkeypatch.setattr(gate().time, "time", lambda: sample["now"])
    with pytest.raises(gate().Refused, match="discovery_changed_during_preflight"):
        gate().run(client, config, 100)


def test_current_config_parser_and_preflight_do_not_mutate_source():
    module = gate()
    config = module.parse_jsonc((module.ROOT / "migration/config/wrangler.brain.jsonc").read_text())
    assert config["name"] == "anticipy-brain"
    assert config["containers"][0]["max_instances"] == 100
    assert config["vars"]["ANTICIPY_MAX_OWNER_WORKERS"] == "100"


@pytest.fixture
def actual_schema():
    database = sqlite3.connect(":memory:")
    database.row_factory = sqlite3.Row
    database.executescript((gate().ROOT / "migration/d1/schema.sql").read_text())
    yield database
    database.close()


@pytest.mark.parametrize("fields", [
    {"status": "external_pending"},
    {"workflow_state": "unknown_state"},
    {"lease_until": "not-a-date", "lease_token": "unresolved-token"},
    {"lease_until": "not-a-date"},
    {"lease_token": "unresolved-token"},
    {"lease_until": "2000-01-01 00:00:00.000Z"},
    {"lease_until": "2000-01-01 00:00:00.000Z", "lease_token": "unresolved-token",
     "claimed_by": "fixture-executor"},
    {"workflow_id": "workflow-fixture", "workflow_state": ""},
    {"workflow_state": "succeeded"},
    {"effect_uncertain": 2},
])
def test_actual_schema_malformed_job_metadata_refuses_instead_of_false_zero(actual_schema, fields):
    row = {"id": "fixturejob000001", "goal": "synthetic task", "status": "queued", **fields}
    actual_schema.execute("INSERT INTO jobs (" + ",".join(row) + ") VALUES ("
                          + ",".join("?" for _ in row) + ")", list(row.values()))
    risk = dict(actual_schema.execute(gate().RISK_SQL).fetchone())
    with pytest.raises(gate().Refused, match="invalid_work_metadata"):
        gate().check_risk(risk)
    assert risk["invalid_metadata"] == 1


@pytest.mark.parametrize("value", [2, -1, "unknown"])
def test_actual_schema_unknown_purge_boolean_refuses(actual_schema, value):
    actual_schema.execute("INSERT INTO purges(id,owner_ref,memory_purged) VALUES(?,?,?)",
                          ("fixturepurge001", "deletedowner001", value))
    risk = dict(actual_schema.execute(gate().RISK_SQL).fetchone())
    with pytest.raises(gate().Refused, match="invalid_work_metadata"):
        gate().check_risk(risk)
    assert risk["invalid_metadata"] == 1


@pytest.mark.parametrize("status,state", [
    ("awaiting_confirm", "draft"), ("awaiting_confirm", "awaiting_approval"),
    ("queued", "queued"), ("needs_user", "needs_user"), ("done", "succeeded"),
    ("failed", "failed"), ("cancelled", "cancelled"),
    ("awaiting_confirm", ""), ("queued", ""), ("needs_user", ""),
    ("done", ""), ("failed", ""), ("cancelled", ""),
])
def test_actual_schema_recognized_resting_and_blank_legacy_states_remain_valid(actual_schema, status, state):
    actual_schema.execute("INSERT INTO jobs(id,goal,status,workflow_state) VALUES(?,?,?,?)",
                          ("fixturejob000001", "synthetic task", status, state))
    risk = dict(actual_schema.execute(gate().RISK_SQL).fetchone())
    gate().check_risk(risk)
    assert risk["invalid_metadata"] == 0


def test_missing_invalid_metadata_measurement_is_not_zero():
    risk = evidence()["risk"]
    del risk["invalid_metadata"]
    with pytest.raises(gate().Refused, match="risk_metadata_invalid"):
        gate().check_risk(risk)


def test_gate_state_pairs_follow_actual_brain_workflow_enum(actual_schema):
    from brain.workflow import LEGACY_STATUS
    for index, (state, status) in enumerate(LEGACY_STATUS.items()):
        running = status == "running"
        actual_schema.execute(
            "INSERT INTO jobs(id,goal,status,workflow_state,workflow_id,lease_token,lease_until,claimed_by) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (f"fixturejob{index:05}", "synthetic task", status, state.value, f"workflow{index:05}",
             "valid-token" if running else "", "2099-01-01 00:00:00.000Z" if running else "",
             "fixture-executor" if running else ""))
    risk = dict(actual_schema.execute(gate().RISK_SQL).fetchone())
    assert risk["invalid_metadata"] == 0
    assert risk["running"] == 1
    with pytest.raises(gate().Refused, match="active_or_uncertain_work"):
        gate().check_risk(risk)
