"""Runtime proof for the account phone-removal boundary.

The iOS button is not a local preference: it must clear both the sign-up seed
and every profile mirror, atomically, before that number can safely belong to a
fresh account. These tests execute the real PocketBase hook body in a small
transactional JSVM stand-in; source-string assertions alone once let a missing
route ship behind a green client test.
"""

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "backend/pb_hooks/phone_remove.pb.js"
SHARE_MIGRATION = ROOT / "backend/pb_migrations/1700000016_share_phone_across_accounts.js"


def run_hook(*, auth=True, collection="owners", profile_count=3,
             legacy_profile_count=0, ref_fallback_profile_count=0,
             foreign_profile_count=0, fail_save_at=0,
             post_verify_fails=False):
    legacy = "legacy-device-owner-old"
    state = {
        "owner": {"id": "owner-old", "phone": "+12025550144",
                  "legacy_uuid": legacy},
        "profiles": [
            {"id": f"profile-{index:03d}", "owner_ref": "owner-old",
             "owner_id": legacy,
             "phone": "+12025550144"}
            for index in range(profile_count)
        ] + [
            {"id": f"legacy-{index:03d}", "owner_ref": "",
             "owner_id": legacy, "phone": "+12025550144"}
            for index in range(legacy_profile_count)
        ] + [
            {"id": f"ref-{index:03d}", "owner_ref": "",
             "owner_id": "owner-old", "phone": "+12025550144"}
            for index in range(ref_fallback_profile_count)
        ] + [
            {"id": f"foreign-{index:03d}", "owner_ref": "",
             "owner_id": "somebody-elses-device", "phone": "+12025550144"}
            for index in range(foreign_profile_count)
        ],
    }
    config = {
        "auth": auth,
        "collection": collection,
        "state": state,
        "failSaveAt": fail_save_at,
        "postVerifyFails": post_verify_fails,
    }
    script = r"""
const fs = require("fs");
const vm = require("vm");
const config = JSON.parse(process.argv[1]);
const source = fs.readFileSync(process.argv[2], "utf8");
let handler = null;
let response = null;
let state = JSON.parse(JSON.stringify(config.state));

function wrap(raw, collectionName) {
  return {
    id: raw.id,
    getString: (key) => String(raw[key] || ""),
    set: (key, value) => { raw[key] = value; },
    collection: () => ({ name: collectionName }),
  };
}

function appFor(target, transactional) {
  let saves = 0;
  return {
    findRecordById: (collection, id) => {
      if (!transactional && config.postVerifyFails) {
        throw new Error("post-commit read unavailable");
      }
      if (collection !== "owners" || target.owner.id !== id) {
        throw new Error("not found");
      }
      return wrap(target.owner, "owners");
    },
    findRecordsByFilter: (collection, filter, sort, limit, offset, params) => {
      if (!transactional && config.postVerifyFails) {
        throw new Error("post-commit read unavailable");
      }
      if (collection !== "owner_profile") return [];
      let rows = target.profiles.filter((row) =>
        row.owner_ref === params.ref ||
        (row.owner_ref === "" &&
         (row.owner_id === params.ref ||
          (params.legacy && row.owner_id === params.legacy))));
      if (String(filter).includes("phone != ''")) {
        rows = rows.filter((row) => String(row.phone || "").trim() !== "");
      }
      rows = rows.slice(offset || 0, (offset || 0) + (limit || rows.length));
      return rows.map((row) => wrap(row, "owner_profile"));
    },
    save: (_record) => {
      saves += 1;
      if (transactional && config.failSaveAt === saves) {
        throw new Error("injected save failure");
      }
    },
  };
}

const outerApp = appFor(state, false);
outerApp.runInTransaction = (callback) => {
  const working = JSON.parse(JSON.stringify(state));
  callback(appFor(working, true));
  state = working;
  const committed = appFor(state, false);
  outerApp.findRecordById = committed.findRecordById;
  outerApp.findRecordsByFilter = committed.findRecordsByFilter;
  outerApp.save = committed.save;
};

const authRecord = config.auth ? {
  id: "owner-old",
  collection: () => ({ name: config.collection }),
} : null;
const event = {
  auth: authRecord,
  app: outerApp,
  json: (status, body) => {
    response = { status, body };
    return response;
  },
};
vm.runInNewContext(source, {
  routerAdd: (_method, _path, callback) => { handler = callback; },
  console: { log: () => {} },
});
if (!handler) throw new Error("route did not register");
handler(event);
process.stdout.write(JSON.stringify({ response, state }));
"""
    completed = subprocess.run(
        ["node", "-e", script, json.dumps(config), str(HOOK)],
        check=True, capture_output=True, text=True,
    )
    return json.loads(completed.stdout)


def test_route_requires_an_owner_account_token():
    assert run_hook(auth=False)["response"]["status"] == 401
    assert run_hook(collection="_superusers")["response"]["status"] == 403


def test_route_clears_the_seed_and_every_profile_beyond_one_page():
    result = run_hook(profile_count=431)
    assert result["response"] == {
        "status": 200,
        "body": {"ok": True, "phone": "", "clearedProfiles": 431},
    }
    assert result["state"]["owner"]["phone"] == ""
    assert {row["phone"] for row in result["state"]["profiles"]} == {""}


def test_route_clears_attributable_ownerless_legacy_rows_but_not_a_stranger():
    result = run_hook(profile_count=2, legacy_profile_count=2,
                      ref_fallback_profile_count=2, foreign_profile_count=1)
    assert result["response"] == {
        "status": 200,
        "body": {"ok": True, "phone": "", "clearedProfiles": 6},
    }
    owned = [row for row in result["state"]["profiles"]
             if row["id"] != "foreign-000"]
    foreign = [row for row in result["state"]["profiles"]
               if row["id"] == "foreign-000"]
    assert {row["phone"] for row in owned} == {""}
    assert [row["phone"] for row in foreign] == ["+12025550144"]


def test_any_save_failure_rolls_the_whole_removal_back():
    result = run_hook(profile_count=205, fail_save_at=75)
    assert result["response"]["status"] == 500
    assert result["response"]["body"]["ok"] is False
    assert result["state"]["owner"]["phone"] == "+12025550144"
    assert {row["phone"] for row in result["state"]["profiles"]} == {
        "+12025550144"}


def test_unknown_post_commit_state_fails_closed():
    result = run_hook(post_verify_fails=True)
    assert result["response"]["status"] == 500
    assert "could not verify" in result["response"]["body"]["message"]


def test_removed_number_is_not_affiliated_and_can_be_reused_by_a_fresh_account():
    result = run_hook(profile_count=4)
    old_claims = [result["state"]["owner"]["phone"]] + [
        row["phone"] for row in result["state"]["profiles"]]
    assert "+12025550144" not in old_claims

    migration = SHARE_MIGRATION.read_text()
    assert "idx_owners_phone" in migration
    assert '.concat(["CREATE INDEX `idx_owners_phone`' in migration
    assert '.concat(["CREATE UNIQUE INDEX `idx_owners_phone`' in migration, (
        "removal freed the old routing rows, but the owners table would still "
        "reject a fresh account reusing that number")


def test_hook_keeps_all_runtime_state_inside_the_registered_handler():
    source = HOOK.read_text()
    before, handler = source.split(
        'routerAdd("POST", "/me/phone/remove", (e) => {', 1)
    assert "const " not in before and "let " not in before and "var " not in before
    assert "runInTransaction((txApp)" in handler
    transaction = handler.split("runInTransaction((txApp) => {", 1)[1].split(
        "});", 1)[0]
    assert "e.app.save" not in transaction
    assert "e.app.find" not in transaction
