"""Independent adversarial proof of the narrow inactive metadata category.

Only an in-memory nullable legacy schema and the actual local filter compiler
are used. These rows remain malformed: no test adopts, cancels, repairs, or
deletes production work, or claims knowledge of historical effects.
"""
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess

import pytest

from proof.audit import brain_deploy_preflight as gate
from tests.test_brain_deploy_preflight import evidence


INACTIVE = "inactive_unowned_unroutable_invalid"


@pytest.fixture
def database():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    # Only the metadata columns consumed by the real risk query. No affinity
    # on numeric inputs: malformed text/blob must not be coerced by the fake.
    db.executescript("""
        CREATE TABLE jobs(status TEXT,workflow_id TEXT,workflow_state TEXT,
          owner_ref TEXT,owner TEXT,lane TEXT,attempts,
          lease_token TEXT,lease_until TEXT,claimed_by TEXT,effect_uncertain);
        CREATE TABLE owners(id TEXT,legacy_uuid TEXT);
        CREATE TABLE purges(owner_ref TEXT,memory_purged);
        CREATE TABLE connection_command_runs(state TEXT);
    """)
    yield db
    db.close()


def orphan():
    return dict(status="queued", workflow_id="fixture-workflow", workflow_state="queued",
                owner_ref="unowned-fixture", owner=None, lane=None, attempts=0,
                lease_token="unresolved-fixture-token", lease_until=None,
                claimed_by=None, effect_uncertain=None)


def insert(db, row):
    db.execute("INSERT INTO jobs (" + ",".join(row) + ") VALUES ("
               + ",".join("?" for _ in row) + ")", list(row.values()))


def measure(db):
    return dict(db.execute(gate.RISK_SQL).fetchone())


@pytest.mark.parametrize("attempts", [0, 0.0])
@pytest.mark.parametrize("uncertainty", [None, 0])
def test_inactive_category_stays_visibly_invalid_and_never_changes_rows(database, attempts, uncertainty):
    row = orphan()
    row.update(attempts=attempts, effect_uncertain=uncertainty)
    insert(database, row)
    before = [tuple(r) for r in database.execute("SELECT * FROM jobs")]
    risk = measure(database)
    assert risk["invalid_metadata"] == risk[INACTIVE] == 1
    sample = evidence()
    sample["risk"] = risk
    result = gate.verify(**sample)
    assert result["unresolved_metadata"] == {"invalid_metadata": 1, INACTIVE: 1}
    assert "unowned-fixture" not in json.dumps(result)
    assert "unresolved-fixture-token" not in json.dumps(result)
    assert [tuple(r) for r in database.execute("SELECT * FROM jobs")] == before


@pytest.mark.parametrize("field,value", [
    ("status", "running"), ("status", "needs_user"), ("status", "failed"),
    ("status", None), ("status", "future-state"),
    ("workflow_state", "running"), ("workflow_state", ""), ("workflow_state", None),
    ("workflow_id", ""), ("workflow_id", None), ("workflow_id", b"invalid-type"),
    ("owner_ref", ""), ("owner_ref", None), ("owner_ref", b"invalid-type"),
    ("owner", ""), ("owner", "legacy-fixture"), ("owner", b"invalid-type"),
    ("lane", ""), ("lane", "browser"), ("lane", "api"), ("lane", "research"),
    ("lane", "device_calendar"), ("lane", "supervised_read"), ("lane", "future-lane"),
    ("attempts", 1), ("attempts", -1), ("attempts", None), ("attempts", "0"),
    ("attempts", b"0"), ("attempts", 0.5),
    ("lease_token", b"invalid-type"),
    ("lease_until", ""), ("lease_until", "2000-01-01T00:00:00Z"),
    ("lease_until", "2099-01-01T00:00:00Z"), ("lease_until", "bad-date"),
    ("claimed_by", ""), ("claimed_by", "fixture-executor"),
    ("effect_uncertain", 1), ("effect_uncertain", 2), ("effect_uncertain", "0"),
    ("effect_uncertain", 0.0), ("effect_uncertain", b"invalid-type"),
])
def test_negating_each_inactive_boundary_never_waives_invalid_work(database, field, value):
    row = orphan()
    row[field] = value
    insert(database, row)
    risk = measure(database)
    assert risk["invalid_metadata"] >= 1
    assert risk[INACTIVE] == 0
    with pytest.raises(gate.Refused):
        gate.check_risk(risk)


@pytest.mark.parametrize("token", [None, ""])
def test_no_lease_token_is_regular_rest_not_the_invalid_category(database, token):
    row = orphan()
    row["lease_token"] = token
    insert(database, row)
    risk = measure(database)
    assert risk["invalid_metadata"] == risk[INACTIVE] == 0
    gate.check_risk(risk)


@pytest.mark.parametrize("relation", ["id", "legacy_uuid", "purge"])
def test_a_real_account_alias_or_even_completed_purge_removes_the_category(database, relation):
    insert(database, orphan())
    if relation == "purge":
        database.execute("INSERT INTO purges VALUES (?,1)", ("unowned-fixture",))
    elif relation == "id":
        database.execute("INSERT INTO owners VALUES (?,?)", ("unowned-fixture", "other-legacy"))
    else:
        database.execute("INSERT INTO owners VALUES (?,?)", ("real-owner", "unowned-fixture"))
    risk = measure(database)
    assert risk["invalid_metadata"] == 1 and risk[INACTIVE] == 0
    with pytest.raises(gate.Refused, match="invalid_work_metadata"):
        gate.check_risk(risk)


def test_unrelated_owner_or_purge_does_not_change_identity_matching(database):
    insert(database, orphan())
    database.execute("INSERT INTO owners VALUES ('other-owner','other-legacy')")
    database.execute("INSERT INTO purges VALUES ('other-owner',1)")
    risk = measure(database)
    assert risk["invalid_metadata"] == risk[INACTIVE] == 1
    gate.check_risk(risk)


@pytest.mark.parametrize("field", ["invalid_metadata", INACTIVE])
@pytest.mark.parametrize("value", [None, False, True, -1, "0", 0.0, float("nan"), float("inf")])
def test_both_measurements_are_strict_counts_never_coerced(field, value):
    risk = evidence()["risk"]
    risk.update(invalid_metadata=1, inactive_unowned_unroutable_invalid=1)
    risk[field] = value
    with pytest.raises(gate.Refused, match="risk_metadata_invalid"):
        gate.check_risk(risk)


@pytest.mark.parametrize("field", ["invalid_metadata", INACTIVE])
def test_missing_count_is_not_an_empty_category(field):
    risk = evidence()["risk"]
    del risk[field]
    with pytest.raises(gate.Refused, match="risk_metadata_invalid"):
        gate.check_risk(risk)


@pytest.mark.parametrize("global_count,inactive_count", [(0, 1), (1, 2), (2, 1)])
def test_subtraction_never_hides_other_invalidity_or_impossible_counts(global_count, inactive_count):
    risk = evidence()["risk"]
    risk.update(invalid_metadata=global_count, inactive_unowned_unroutable_invalid=inactive_count)
    with pytest.raises(gate.Refused):
        gate.check_risk(risk)


@pytest.mark.parametrize("field", ["running", "claimed", "live_leases", "uncertain_active",
                                   "connector_pending", "pending_purges"])
def test_inactive_metadata_does_not_waive_any_active_counter(field):
    risk = evidence()["risk"]
    risk.update(invalid_metadata=1, inactive_unowned_unroutable_invalid=1)
    risk[field] = 1
    with pytest.raises(gate.Refused, match="active_or_uncertain_work"):
        gate.check_risk(risk)


def _function(source, name):
    return next(node for node in ast.parse(source).body
                if isinstance(node, ast.FunctionDef) and node.name == name)


def _filter(source, name, substitutions):
    function = _function(source, name)
    expression = next(node.value for node in ast.walk(function)
                      if isinstance(node, ast.Assign) and any(
                          isinstance(target, ast.Name) and target.id == "filt"
                          for target in node.targets))
    def literal(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.JoinedStr):
            return "".join(literal(part) for part in node.values)
        assert isinstance(node, ast.FormattedValue) and isinstance(node.value, ast.Name)
        assert node.conversion == -1 and node.format_spec is None
        return substitutions[node.value.id]
    return literal(expression)


def test_actual_executor_selectors_still_exclude_null_lanes_in_shallow_ci():
    """Selector anchors were independently read at e6161de2 on 2026-09-13.

    They match the candidate. Keep these tiny anchors in the test rather than
    fetching historical Git objects in shallow CI. A routing/schema change
    requires re-review of the inactive category, not refreshing hashes blindly.
    """
    root = Path(__file__).resolve().parents[1]
    worker = (root / "brain/worker.py").read_text()
    browser = (root / "extension/background.js").read_text()
    native = (root / "app/ios/Anticipy/Backend/NativeCalendarHand.swift").read_text()
    browser_block = re.search(r"const BROWSER_LANE =[^\n]*\nconst ownerLaneFilter =[^\n]*\n[^\n]*;", browser).group()
    native_block = re.search(r"        let filter = .*?\n        var page = 1", native, re.S).group()
    assert hashlib.sha256(browser_block.encode()).hexdigest() == "b328db77d1028fe6590dfa1db50e8d9ee0f02560faebe7b245f65a5d05cf7a99"
    assert hashlib.sha256(native_block.encode()).hexdigest() == "b3a7b759d0f5118301840fdc0aa9637acc15d4995a9f56f0db7e71fd4a2c7c0c"
    from brain import worker as actual_worker
    api_filter = _filter(worker, "run_api_jobs", {"LANE_API": actual_worker.LANE_API})
    research_filter = _filter(worker, "run_research_jobs", {})
    assert api_filter == 'status="queued" && lane="api"'
    assert research_filter == 'status="queued" && lane="research"'
    recovery = _filter(worker, "_recover_one_read", {"owner": "unowned-fixture"})
    assert recovery == ('owner_ref="unowned-fixture" && status="queued" && consequence="read_only" '
                        '&& (lane="" || lane="browser")')
    # Exercise the actual current owner helper as well: a populated canonical
    # owner does not fall through to legacy UUID; an empty one needs legacy ID.
    from brain.worker import owner_filter
    from types import SimpleNamespace
    assert owner_filter(SimpleNamespace(owner_ref="real-owner", owner_id="old-owner")) == 'owner_ref="real-owner"'
    assert owner_filter(SimpleNamespace(owner_ref="", owner_id="old-owner")) == 'owner="old-owner"'
    assert owner_filter(SimpleNamespace(owner_ref="", owner_id="")) == ""
    selectors = [
        'status="queued" && owner_ref="unowned-fixture" && workflow_id!="" && lane!="research" && lane!="api" && lane!="device_calendar" && lane!="supervised_read"',
        api_filter, research_filter, recovery,
        'owner_ref="unowned-fixture" && lane!="" && lane!="research" && lane!="api" && lane!="supervised_read" && status!="done" && status!="failed" && status!="cancelled"',
    ]
    node = shutil.which("node")
    assert node, "Node is required to prove the actual Worker filter semantics"
    script = r"""
      import assert from 'node:assert/strict';
      import { DatabaseSync } from 'node:sqlite';
      import { filterToSQL } from './migration/workers/filter-dsl.ts';
      import { COLLECTIONS } from './migration/workers/src/api/schema.ts';
      const selectors = JSON.parse(process.argv[1]);
      const db = new DatabaseSync(':memory:');
      db.exec('CREATE TABLE jobs(status TEXT, owner_ref TEXT, lane TEXT, workflow_id TEXT, consequence TEXT)');
      db.prepare('INSERT INTO jobs VALUES(?,?,?,?,?)').run('queued','unowned-fixture',null,'fixture-workflow','read_only');
      for (const filter of selectors) {
        const query = filterToSQL(filter, {schema: COLLECTIONS.jobs.columns});
        assert(!query.sql.includes('COALESCE'));
        assert.equal(db.prepare('SELECT count(*) AS n FROM jobs WHERE '+query.sql).get(...query.params).n, 0);
      }
      // Positive mutant control: normalizing NULL lane to browser-empty would
      // select this row, invalidating the category's structural premise.
      const normalized = {...COLLECTIONS.jobs.columns, lane: {...COLLECTIONS.jobs.columns.lane, nullable:true}};
      const mutant = filterToSQL(selectors[0], {schema:normalized});
      assert.equal(db.prepare('SELECT count(*) AS n FROM jobs WHERE '+mutant.sql).get(...mutant.params).n, 1);
      db.close();
      console.log('null-lane-exclusion-proved');
    """
    env = {key: os.environ[key] for key in ("PATH", "TMPDIR", "SYSTEMROOT") if key in os.environ}
    result = subprocess.run([node, "--experimental-strip-types", "--input-type=module", "-e", script,
                             json.dumps(selectors)], cwd=root, env=env,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "null-lane-exclusion-proved"
