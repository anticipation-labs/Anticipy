"""Runtime proof for the canonical owner-profile write boundary.

The profile screen intentionally saves phone and identity details separately.
These tests execute the real PocketBase hook and migration bodies inside a
transactional Node JSVM stand-in, rather than asserting that reassuring source
words exist. Python's SQLite runtime also executes the exact landed unique-index
SQL, because the race is not closed until the storage engine refuses a second
nonempty ``owner_ref``.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "backend/pb_hooks/owner_profile_upsert.pb.js"
MIGRATION = (
    ROOT
    / "backend/pb_migrations/1700000054_owner_profile_canonical.js"
)


def _profile(
    row_id: str,
    *,
    owner_ref: str = "owner-a",
    owner_id: str = "device-a",
    updated: str = "2026-08-30 10:00:00.000Z",
    created: str = "2026-08-30 09:00:00.000Z",
    phone: str = "",
    first_name: str = "",
    last_name: str = "",
    email: str = "",
    birthday: str = "",
    timezone: str = "",
    name: str = "",
    facts: str = "",
) -> dict[str, str]:
    return {
        "id": row_id,
        "owner_ref": owner_ref,
        "owner_id": owner_id,
        "updated": updated,
        "created": created,
        "phone": phone,
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "birthday": birthday,
        "timezone": timezone,
        "name": name,
        "facts": facts,
    }


def run_hook(
    requests: list[dict] | None = None,
    *,
    profiles: list[dict] | None = None,
    owner: dict | None = None,
    transaction_list_fails: bool = False,
    transaction_owner_fails: bool = False,
    fail_save_at: int = 0,
    fail_delete_at: int = 0,
    post_verify_fails: bool = False,
    enforce_unique: bool = True,
) -> dict:
    """Run one or more requests against the real hook in one shared DB."""

    config = {
        "requests": requests or [{"body": {}}],
        "state": {
            "owner": owner
            or {
                "id": "owner-a",
                "email": "account@example.com",
                "phone": "+16045550100",
                "legacy_uuid": "device-a",
            },
            "profiles": profiles or [],
            "clock": 0,
        },
        "transactionListFails": transaction_list_fails,
        "transactionOwnerFails": transaction_owner_fails,
        "failSaveAt": fail_save_at,
        "failDeleteAt": fail_delete_at,
        "postVerifyFails": post_verify_fails,
        "enforceUnique": enforce_unique,
    }
    script = r"""
const fs = require("fs");
const vm = require("vm");
const config = JSON.parse(process.argv[1]);
const source = fs.readFileSync(process.argv[2], "utf8");
let handler = null;
let state = JSON.parse(JSON.stringify(config.state));
const responses = [];

function wrap(raw, collectionName) {
  return {
    get id() { return String(raw.id || ""); },
    _raw: raw,
    _collectionName: collectionName,
    getString: (key) => String(raw[key] || ""),
    set: (key, value) => { raw[key] = value; },
    collection: () => ({ name: collectionName }),
  };
}

function sortedProfiles(rows) {
  return rows.slice().sort((left, right) => {
    for (const key of ["updated", "created", "id"]) {
      const compared = String(right[key] || "").localeCompare(String(left[key] || ""));
      if (compared !== 0) return compared;
    }
    return 0;
  });
}

function appFor(target, transactional) {
  let saves = 0;
  let deletes = 0;
  return {
    findCollectionByNameOrId: (name) => {
      if (name !== "owner_profile") throw new Error("unknown collection");
      return { name };
    },
    findRecordById: (collection, id) => {
      if (transactional && config.transactionOwnerFails) {
        throw new Error("owner read unavailable");
      }
      if (!transactional && config.postVerifyFails) {
        throw new Error("post-commit read unavailable");
      }
      if (collection !== "owners" || target.owner.id !== id) {
        throw new Error("not found");
      }
      return wrap(target.owner, "owners");
    },
    findRecordsByFilter: (collection, filter, sort, limit, offset, params) => {
      if (transactional && config.transactionListFails) {
        throw new Error("profile list unavailable");
      }
      if (!transactional && config.postVerifyFails) {
        throw new Error("post-commit read unavailable");
      }
      if (collection !== "owner_profile") return [];
      let rows = target.profiles;
      if (params && params.ref !== undefined) {
        rows = rows.filter((row) => row.owner_ref === params.ref);
      } else if (String(filter).includes("owner_ref != ''")) {
        rows = rows.filter((row) => String(row.owner_ref || "") !== "");
      }
      rows = sortedProfiles(rows);
      const start = offset || 0;
      const end = limit > 0 ? start + limit : rows.length;
      return rows.slice(start, end).map((row) => wrap(row, "owner_profile"));
    },
    save: (record) => {
      saves += 1;
      if (transactional && config.failSaveAt === saves) {
        throw new Error("injected save failure");
      }
      const raw = record._raw;
      if (record._collectionName !== "owner_profile") {
        throw new Error("unexpected save collection");
      }
      if (config.enforceUnique && String(raw.owner_ref || "") !== "") {
        const collision = target.profiles.some(
          (row) => row !== raw && row.id !== raw.id && row.owner_ref === raw.owner_ref);
        if (collision) throw new Error("UNIQUE owner_profile.owner_ref");
      }
      if (!raw.id) {
        raw.id = "profile-" + String(target.profiles.length + 1).padStart(3, "0");
        raw.created = "2026-09-01 12:00:00.000Z";
        target.profiles.push(raw);
      }
      target.clock += 1;
      raw.updated = "2026-09-01 12:00:" + String(target.clock).padStart(2, "0") + ".000Z";
    },
    delete: (record) => {
      deletes += 1;
      if (transactional && config.failDeleteAt === deletes) {
        throw new Error("injected delete failure");
      }
      const index = target.profiles.findIndex((row) => row.id === record.id);
      if (index < 0) throw new Error("delete target missing");
      target.profiles.splice(index, 1);
    },
  };
}

function Record(collection) {
  return wrap({ id: "", created: "", updated: "" }, collection.name);
}

let outerApp = appFor(state, false);
function runInTransaction(callback) {
  const working = JSON.parse(JSON.stringify(state));
  callback(appFor(working, true));
  state = working;
  outerApp = appFor(state, false);
  outerApp.runInTransaction = runInTransaction;
}
outerApp.runInTransaction = runInTransaction;

vm.runInNewContext(source, {
  routerAdd: (_method, _path, callback) => { handler = callback; },
  Record,
  console: { log: () => {} },
});
if (!handler) throw new Error("route did not register");

for (const request of config.requests) {
  let response = null;
  const auth = request.auth === false ? null : {
    id: state.owner.id,
    collection: () => ({ name: request.collection || "owners" }),
  };
  const event = {
    auth,
    get app() { return outerApp; },
    requestInfo: () => {
      if (request.bodyReadFails) throw new Error("body unavailable");
      return { body: request.body };
    },
    json: (status, body) => {
      response = { status, body };
      return response;
    },
  };
  handler(event);
  responses.push(response);
}
process.stdout.write(JSON.stringify({ responses, state }));
"""
    completed = subprocess.run(
        ["node", "-e", script, json.dumps(config), str(HOOK)],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def run_migration(
    profiles: list[dict],
    *,
    indexes: list[str] | None = None,
    list_fails: bool = False,
    fail_delete_at: int = 0,
    fail_index_save: bool = False,
) -> dict:
    """Execute the real migration callback with migration-runner rollback."""

    config = {
        "state": {"profiles": profiles, "indexes": indexes or []},
        "listFails": list_fails,
        "failDeleteAt": fail_delete_at,
        "failIndexSave": fail_index_save,
    }
    script = r"""
const fs = require("fs");
const vm = require("vm");
const config = JSON.parse(process.argv[1]);
const source = fs.readFileSync(process.argv[2], "utf8");
let up = null;
let down = null;
let state = JSON.parse(JSON.stringify(config.state));

function wrap(raw) {
  return {
    get id() { return String(raw.id || ""); },
    _raw: raw,
    getString: (key) => String(raw[key] || ""),
  };
}

function sorted(rows) {
  return rows.slice().sort((left, right) => {
    for (const key of ["updated", "created", "id"]) {
      const compared = String(right[key] || "").localeCompare(String(left[key] || ""));
      if (compared !== 0) return compared;
    }
    return 0;
  });
}

function appFor(target) {
  let deletes = 0;
  const collection = { name: "owner_profile", indexes: target.indexes };
  return {
    findRecordsByFilter: (name, filter) => {
      if (config.listFails) throw new Error("migration list unavailable");
      if (name !== "owner_profile") return [];
      return sorted(target.profiles)
        .filter((row) => !String(filter).includes("owner_ref != ''") || row.owner_ref)
        .map(wrap);
    },
    findCollectionByNameOrId: (name) => {
      if (name !== "owner_profile") throw new Error("unknown collection");
      collection.indexes = target.indexes;
      return collection;
    },
    delete: (record) => {
      deletes += 1;
      if (config.failDeleteAt === deletes) throw new Error("injected delete failure");
      const index = target.profiles.findIndex((row) => row.id === record.id);
      if (index < 0) throw new Error("delete target missing");
      target.profiles.splice(index, 1);
    },
    save: (model) => {
      if (config.failIndexSave) throw new Error("injected index save failure");
      const unique = (model.indexes || []).some(
        (index) => String(index).includes("idx_owner_profile_owner_ref") &&
          String(index).includes("CREATE UNIQUE INDEX"));
      if (unique) {
        const seen = new Set();
        for (const row of target.profiles) {
          if (!row.owner_ref) continue;
          if (seen.has(row.owner_ref)) throw new Error("UNIQUE owner_profile.owner_ref");
          seen.add(row.owner_ref);
        }
      }
      target.indexes = (model.indexes || []).slice();
      collection.indexes = target.indexes;
    },
  };
}

vm.runInNewContext(source, {
  migrate: (upCallback, downCallback) => { up = upCallback; down = downCallback; },
  console: { log: () => {} },
});
if (!up || !down) throw new Error("migration did not register both directions");

let error = "";
const working = JSON.parse(JSON.stringify(state));
try {
  up(appFor(working));
  state = working;
} catch (caught) {
  error = String(caught);
}
process.stdout.write(JSON.stringify({ state, error }));
"""
    completed = subprocess.run(
        ["node", "-e", script, json.dumps(config), str(MIGRATION)],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def test_route_requires_the_authenticated_owner_collection() -> None:
    assert run_hook([{"auth": False, "body": {}}])["responses"][0]["status"] == 401
    assert (
        run_hook([{"collection": "_superusers", "body": {}}])["responses"][0]["status"]
        == 403
    )


def test_fresh_account_details_only_preserve_account_phone_and_email() -> None:
    result = run_hook(
        [
            {
                "body": {
                    "first_name": "Omar",
                    "last_name": "Ebrahim",
                    "birthday": "1990-01-02",
                    "timezone": "America/Vancouver",
                }
            }
        ]
    )
    response = result["responses"][0]
    assert response["status"] == 200
    assert len(result["state"]["profiles"]) == 1
    profile = response["body"]["profile"]
    assert profile["owner_ref"] == "owner-a"
    assert profile["owner_id"] == "device-a"
    assert profile["email"] == "account@example.com"
    assert profile["phone"] == "+16045550100"
    assert profile["first_name"] == "Omar"
    assert profile["last_name"] == "Ebrahim"
    assert profile["birthday"] == "1990-01-02"
    assert profile["timezone"] == "America/Vancouver"


def test_fresh_account_phone_only_preserves_account_email() -> None:
    result = run_hook([{"body": {"phone": "+16045550222"}}])
    response = result["responses"][0]
    assert response["status"] == 200
    profile = response["body"]["profile"]
    assert profile["phone"] == "+16045550222"
    assert profile["email"] == "account@example.com"
    assert profile["first_name"] == ""
    assert profile["last_name"] == ""


def test_omission_preserves_canonical_empty_instead_of_resurrecting_account_seed() -> None:
    existing = _profile(
        "profile-new",
        phone="",
        email="",
        first_name="Existing",
    )
    result = run_hook(
        [{"body": {"last_name": "Person"}}],
        profiles=[existing],
    )
    profile = result["responses"][0]["body"]["profile"]
    assert profile["phone"] == ""
    assert profile["email"] == ""
    assert profile["first_name"] == "Existing"
    assert profile["last_name"] == "Person"


def test_explicit_empty_clears_but_omitted_fields_survive() -> None:
    existing = _profile(
        "profile-new",
        phone="+16045550333",
        email="saved@example.com",
        first_name="Saved",
        timezone="Europe/London",
    )
    result = run_hook(
        [{"body": {"phone": ""}}],
        profiles=[existing],
    )
    profile = result["responses"][0]["body"]["profile"]
    assert profile["phone"] == ""
    assert profile["email"] == "saved@example.com"
    assert profile["first_name"] == "Saved"
    assert profile["timezone"] == "Europe/London"


def test_back_to_back_partial_first_writes_merge_into_one_complete_row() -> None:
    result = run_hook(
        [
            {
                "body": {
                    "first_name": "Omar",
                    "last_name": "Ebrahim",
                    "email": "founder@example.test",
                }
            },
            {"body": {"phone": "+12025550144"}},
        ],
        owner={
            "id": "owner-a",
            "email": "account@example.com",
            "phone": "",
            "legacy_uuid": "device-a",
        },
    )
    assert [response["status"] for response in result["responses"]] == [200, 200]
    assert len(result["state"]["profiles"]) == 1
    profile = result["state"]["profiles"][0]
    assert profile["first_name"] == "Omar"
    assert profile["last_name"] == "Ebrahim"
    assert profile["email"] == "founder@example.test"
    assert profile["phone"] == "+12025550144"


def test_duplicate_cleanup_keeps_newest_row_exactly_without_value_merging() -> None:
    older = _profile(
        "profile-old",
        updated="2026-08-30 08:00:00.000Z",
        phone="+16049999999",
        email="old@example.com",
        first_name="Old",
    )
    newest = _profile(
        "profile-new",
        updated="2026-08-30 12:00:00.000Z",
        phone="",
        email="",
        first_name="Newest",
    )
    result = run_hook(
        [{"body": {"timezone": "America/Vancouver"}}],
        profiles=[older, newest],
        enforce_unique=False,
    )
    response = result["responses"][0]
    assert response["status"] == 200
    assert response["body"]["removedDuplicates"] == 1
    assert [row["id"] for row in result["state"]["profiles"]] == ["profile-new"]
    profile = response["body"]["profile"]
    assert profile["phone"] == ""
    assert profile["email"] == ""
    assert profile["first_name"] == "Newest"
    assert profile["timezone"] == "America/Vancouver"


def test_owner_id_is_not_client_editable_or_usable_as_a_device_injection() -> None:
    result = run_hook([{"body": {"owner_id": "somebody-elses-device"}}])
    assert result["responses"][0]["status"] == 400
    assert result["state"]["profiles"] == []

    existing = _profile("profile-new", owner_id="device-a")
    second = run_hook(
        [{"body": {"owner_id": "somebody-elses-device", "phone": "+16045550999"}}],
        profiles=[existing],
    )
    assert second["responses"][0]["status"] == 400
    assert second["state"]["profiles"][0]["owner_id"] == "device-a"
    assert second["state"]["profiles"][0]["phone"] == ""


def test_owner_ref_is_derived_from_auth_and_cannot_be_injected() -> None:
    result = run_hook(
        [{"body": {"owner_ref": "owner-b", "first_name": "Must not land"}}]
    )
    assert result["responses"][0]["status"] == 400
    assert result["state"]["profiles"] == []

    existing = _profile("profile-new", owner_ref="owner-a", first_name="Original")
    second = run_hook(
        [{"body": {"owner_ref": "owner-b", "first_name": "Moved"}}],
        profiles=[existing],
    )
    assert second["responses"][0]["status"] == 400
    assert second["state"]["profiles"][0]["owner_ref"] == "owner-a"
    assert second["state"]["profiles"][0]["first_name"] == "Original"


def test_unknown_list_or_owner_read_never_falls_through_to_create() -> None:
    list_unknown = run_hook(
        [{"body": {"first_name": "Must not land"}}],
        transaction_list_fails=True,
    )
    assert list_unknown["responses"][0]["status"] == 500
    assert list_unknown["state"]["profiles"] == []

    owner_unknown = run_hook(
        [{"body": {"phone": "+16045550777"}}],
        transaction_owner_fails=True,
    )
    assert owner_unknown["responses"][0]["status"] == 500
    assert owner_unknown["state"]["profiles"] == []


def test_save_or_duplicate_delete_failure_rolls_the_whole_write_back() -> None:
    older = _profile(
        "profile-old",
        updated="2026-08-30 08:00:00.000Z",
        first_name="Old",
    )
    newest = _profile(
        "profile-new",
        updated="2026-08-30 12:00:00.000Z",
        first_name="Newest",
    )
    original = [older, newest]

    delete_failure = run_hook(
        [{"body": {"first_name": "Changed"}}],
        profiles=original,
        fail_delete_at=1,
        enforce_unique=False,
    )
    assert delete_failure["responses"][0]["status"] == 500
    assert delete_failure["state"]["profiles"] == original

    save_failure = run_hook(
        [{"body": {"first_name": "Changed"}}],
        profiles=original,
        fail_save_at=1,
        enforce_unique=False,
    )
    assert save_failure["responses"][0]["status"] == 500
    assert save_failure["state"]["profiles"] == original


def test_unknown_post_commit_read_fails_closed() -> None:
    result = run_hook(
        [{"body": {"first_name": "Committed but unverified"}}],
        post_verify_fails=True,
    )
    assert result["responses"][0]["status"] == 500
    assert len(result["state"]["profiles"]) == 1
    assert result["state"]["profiles"][0]["first_name"] == "Committed but unverified"


def test_migration_keeps_exact_newest_rows_and_installs_unique_index() -> None:
    rows = [
        _profile(
            "a-old",
            updated="2026-08-30 08:00:00.000Z",
            phone="+16041111111",
            email="old-a@example.com",
        ),
        _profile(
            "a-new",
            updated="2026-08-30 12:00:00.000Z",
            phone="",
            email="",
            first_name="Canonical A",
        ),
        _profile(
            "b-only",
            owner_ref="owner-b",
            owner_id="device-b",
            first_name="Canonical B",
        ),
        _profile(
            "orphan",
            owner_ref="",
            owner_id="legacy-orphan",
            first_name="Not owned yet",
        ),
    ]
    result = run_migration(rows)
    assert result["error"] == ""
    by_id = {row["id"]: row for row in result["state"]["profiles"]}
    assert set(by_id) == {"a-new", "b-only", "orphan"}
    assert by_id["a-new"]["phone"] == ""
    assert by_id["a-new"]["email"] == ""
    assert by_id["a-new"]["first_name"] == "Canonical A"
    assert any(
        "CREATE UNIQUE INDEX" in index
        and "idx_owner_profile_owner_ref" in index
        and "WHERE `owner_ref` != ''" in index
        for index in result["state"]["indexes"]
    )


@pytest.mark.parametrize(
    "failure",
    [
        {"fail_delete_at": 1},
        {"fail_index_save": True},
        {"list_fails": True},
    ],
)
def test_migration_failure_rolls_back_cleanup_and_index(failure: dict) -> None:
    rows = [
        _profile("a-old", updated="2026-08-30 08:00:00.000Z"),
        _profile("a-new", updated="2026-08-30 12:00:00.000Z"),
    ]
    result = run_migration(rows, indexes=["CREATE INDEX existing ON owner_profile (phone)"], **failure)
    assert result["error"]
    assert result["state"] == {
        "profiles": rows,
        "indexes": ["CREATE INDEX existing ON owner_profile (phone)"],
    }


def test_landed_index_sql_executes_and_refuses_two_first_rows() -> None:
    migrated = run_migration([])
    [index_sql] = [
        index
        for index in migrated["state"]["indexes"]
        if "idx_owner_profile_owner_ref" in index
    ]

    database = sqlite3.connect(":memory:")
    database.execute("CREATE TABLE owner_profile (owner_ref TEXT NOT NULL DEFAULT '')")
    database.execute(index_sql)
    database.execute("INSERT INTO owner_profile(owner_ref) VALUES ('owner-a')")
    with pytest.raises(sqlite3.IntegrityError):
        database.execute("INSERT INTO owner_profile(owner_ref) VALUES ('owner-a')")
    # Legacy ownerless rows remain adoptable and are deliberately outside the
    # partial uniqueness boundary.
    database.execute("INSERT INTO owner_profile(owner_ref) VALUES ('')")
    database.execute("INSERT INTO owner_profile(owner_ref) VALUES ('')")


def test_hook_keeps_runtime_state_inside_handler_and_uses_tx_app_only() -> None:
    source = HOOK.read_text()
    before, handler = source.split(
        'routerAdd("POST", "/me/profile/upsert", (e) => {', 1
    )
    assert "const " not in before and "let " not in before and "var " not in before
    assert "runInTransaction((txApp)" in handler
    transaction = handler.split("runInTransaction((txApp) => {", 1)[1].split(
        "    });", 1
    )[0]
    assert "e.app.save" not in transaction
    assert "e.app.delete" not in transaction
    assert "e.app.find" not in transaction
    assert ".findFirstRecordByFilter(" not in transaction
