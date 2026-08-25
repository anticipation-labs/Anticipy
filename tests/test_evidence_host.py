"""An evidence picture needs a HOST, and the host must not become a CDN.

WHAT THIS CLOSES.  `workflow_guard.pb.js` already refuses any transition to
`done` without a receipt whose `verified` is true and whose `evidence` array is
non-empty (workflow_guard.pb.js:202-211).  Verified by reading it: the evidence
it demands is a list of STRINGS — `url:…`, `title:…`, `page:<hash>`, `facts:…`,
`proof:…` (extension/agent_loop.js:1728-1748) — an audit index, not a picture.
The browser CAN take a picture (`screenshot()`, extension/agent_loop.js:105-143,
a half-scale quality-45 JPEG capped at 400 KB) and throws it away after one
model call.  `VoiceArm.text()` posts exactly From/To/Body
(brain/voice_arm.py:410-420).  Zero `type: "file"` fields across 47 migrations.

So "done-text with photo" was never blocked on Twilio's `MediaUrl` parameter.
It was blocked on there being nowhere for the bytes to live, and no URL Twilio
could fetch them from.  This file pins the host.

WHY EVERY CHECK BELOW IS BEHAVIOURAL WHERE IT CAN BE.  A grep for a constant
proves a constant was typed.  It does not prove the gate refuses anything, and
this repository's recorded failure mode is exactly that: gates that pass while
the thing they guard is wide open.  So the fetch gate is loaded into an
isolated V8 context and DRIVEN — a request at a time, with the record present,
absent, expired, spent, and addressed by collection id instead of by name.

THE ISOLATED CONTEXT IS NOT DECORATION EITHER.  A `const` declared at the top
of a pb_hooks file is NOT in scope inside a routerAdd/routerUse callback; the
PocketBase JSVM gives each handler its own execution context.  That cost the
whole account-delete feature once (account_delete.pb.js:42-56, measured against
a local PocketBase 0.30.4) and password_reset.pb.js:23-26 and
audit_retention.pb.js:24-27 both carry the same warning.  Re-running the
captured handler source in a FRESH context, with only the globals PocketBase
actually exposes, is the only way a test can catch it before production does.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "backend" / "pb_hooks"
MIGRATIONS = ROOT / "backend" / "pb_migrations"
EVIDENCE_HOOK = HOOKS / "evidence.pb.js"
EVIDENCE_MIGRATION = MIGRATIONS / "1700000045_evidence.js"
SERVICE_TOKEN = "service-token-for-tests"


# --------------------------------------------------------------- the harness

HARNESS = r"""
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const args = process.argv.slice(-2);
const scenario = JSON.parse(args[0]);
const HOOKS = args[1];

const logs = [];
const saved = [];
const deleted = [];

// Only what PocketBase actually exposes to a hook runtime. Anything the hook
// reaches for that is not here is a ReferenceError in production too.
const globals = () => ({
  $os: { getenv: (name) => (scenario.env || {})[name] || "" },
  $security: { sha256: (v) => "sha256:" + String(v) },
  console: { log: (...parts) => logs.push(parts.map(String).join(" ")) },
});

let useSource = null;
let shareSource = null;
let sweepSource = null;
let sweepCollection = null;

const loader = Object.assign(globals(), {
  routerUse: (fn) => { useSource = String(fn); },
  routerAdd: (method, route, fn) => {
    if (route === '/evidence/share') shareSource = String(fn);
  },
  onRecordAfterCreateSuccess: (fn, collection) => {
    sweepSource = String(fn);
    sweepCollection = collection;
  },
});
vm.createContext(loader);
vm.runInContext(fs.readFileSync(path.join(HOOKS, scenario.hook), 'utf8'), loader);

const want = { use: useSource, share: shareSource, sweep: sweepSource }[scenario.handler];
if (!want) {
  process.stdout.write(JSON.stringify({ error: 'handler ' + scenario.handler + ' was never registered' }));
  process.exit(0);
}

// FRESH context: nothing the module body declared is visible here, exactly as
// in the PocketBase JSVM.
const isolated = globals();
vm.createContext(isolated);
const handler = vm.runInContext('(' + want + ')', isolated);

const mkRecord = (data) => ({
  id: data.id,
  get: (k) => data[k],
  getString: (k) => (data[k] === undefined || data[k] === null) ? "" : String(data[k]),
  getBool: (k) => !!data[k],
  set: (k, v) => { data[k] = v; },
  data: data,
});

const rows = (scenario.rows || []).map(mkRecord);
const byId = {};
for (const r of rows) byId[r.id] = r;

const app = {
  findCollectionByNameOrId: (key) => {
    const map = scenario.collections || {};
    if (map[key] === 'throw') throw new Error('no such collection');
    if (!map[key]) throw new Error('no such collection');
    return { id: map[key].id, name: map[key].name };
  },
  findRecordById: (collection, id) => {
    if (scenario.lookupThrows) throw new Error('database hiccup');
    const rec = byId[id];
    if (!rec || rec.data.collection !== collection) throw new Error('no rows');
    return rec;
  },
  findFirstRecordByFilter: (collection, filter, params) => {
    if (scenario.lookupThrows) throw new Error('database hiccup');
    const p = params || {};
    for (const r of rows) {
      if (r.data.collection !== collection) continue;
      if (p.id !== undefined && r.data.agent_id !== p.id) continue;
      if (p.token !== undefined && r.data.agent_token !== p.token) continue;
      if (p.code !== undefined && r.data.pair_code !== p.code) continue;
      return r;
    }
    throw new Error('no rows');
  },
  findRecordsByFilter: (collection, filter, sort, limit, offset, params) => {
    if (scenario.filterThrows) throw new Error('database hiccup');
    let out = rows.filter((r) => r.data.collection === collection);
    const owner = params && (params.o || params.owner);
    if (owner) out = out.filter((r) => r.data.owner_ref === owner);
    out.sort((a, b) => String(b.data.created || '').localeCompare(String(a.data.created || '')));
    return out.slice(offset || 0, (offset || 0) + (limit || out.length));
  },
  save: (rec) => {
    if (scenario.saveFails) throw new Error('disk I/O error');
    saved.push(JSON.parse(JSON.stringify(rec.data)));
  },
  delete: (rec) => {
    if (scenario.deleteFails) throw new Error('disk I/O error');
    deleted.push(rec.id);
  },
};

const headers = scenario.headers || {};
let outcome = 'none';
let status = 0;
let body = null;

const e = {
  next: () => { outcome = 'next'; return 'NEXT'; },
  json: (s, b) => { outcome = 'json'; status = s; body = b; return 'JSON'; },
  app: app,
  auth: scenario.auth ? {
    id: scenario.auth.id,
    collection: () => ({ name: scenario.auth.collection }),
  } : null,
  hasSuperuserAuth: () => !!scenario.superuser,
  realIP: () => '203.0.113.7',
  requestInfo: () => ({ body: scenario.body || {} }),
  record: scenario.newRecord ? mkRecord(scenario.newRecord) : null,
  request: {
    method: scenario.method || 'GET',
    url: {
      path: scenario.path || '/',
      query: () => ({ get: (k) => (scenario.query || {})[k] || '' }),
    },
    header: { get: (k) => headers[k] || '' },
  },
};

let threw = null;
try { handler(e); } catch (err) { threw = String(err); }
process.stdout.write(JSON.stringify({
  outcome: outcome, status: status, body: body,
  saved: saved, deleted: deleted, logs: logs, threw: threw,
  sweepCollection: sweepCollection,
}));
"""


def drive(**scenario) -> dict:
    scenario.setdefault("hook", "evidence.pb.js")
    scenario.setdefault("handler", "use")
    scenario.setdefault("env", {"ANTICIPY_SERVICE_TOKEN": SERVICE_TOKEN,
                                "ANTICIPY_PUBLIC_URL": "https://backend.example"})
    proc = subprocess.run(
        ["node", "-e", HARNESS, "--", json.dumps(scenario), str(HOOKS)],
        capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise AssertionError(f"harness failed: {proc.stderr[-3000:]}")
    out = json.loads(proc.stdout)
    if out.get("error"):
        raise AssertionError(out["error"])
    assert out["threw"] is None, f"the handler threw in an isolated context: {out['threw']}"
    return out


def evidence_row(**over) -> dict:
    row = {
        "collection": "evidence", "id": "ev0000000000001",
        "owner_ref": "own1", "job": "job0000000000001",
        "image": "shot_a1b2c3d4e5.jpg", "share_expires": "", "fetches": 0,
        "created": "2026-08-25T00:00:00Z",
    }
    row.update(over)
    return row


COLLECTIONS = {
    "evidence": {"id": "pbc_evidence001", "name": "evidence"},
    "pbc_evidence001": {"id": "pbc_evidence001", "name": "evidence"},
    "events": {"id": "pbc_events00001", "name": "events"},
    "pbc_events00001": {"id": "pbc_events00001", "name": "events"},
}


def fetch(row=None, *, key="evidence", headers=None, **over) -> dict:
    rows = [] if row is None else [row]
    record_id = (row or {}).get("id", "ev0000000000001")
    filename = (row or {}).get("image", "shot_a1b2c3d4e5.jpg")
    scenario = {
        "handler": "use",
        "path": f"/api/files/{key}/{record_id}/{filename}",
        "collections": COLLECTIONS,
        "rows": rows,
        "headers": headers or {},
    }
    scenario.update(over)
    return drive(**scenario)


FUTURE = "2099-01-01T00:00:00Z"
PAST = "2000-01-01T00:00:00Z"


def migration_code() -> str:
    """The migration with its comments stripped.

    Not fussiness: the header explains the bug by quoting `type: "file"` in a
    sentence about there being none, and a check that cannot tell prose from a
    field definition passed with the field mutated away. Found by mutating it.
    """
    raw = EVIDENCE_MIGRATION.read_text()
    return "\n".join(line.split("//", 1)[0] for line in raw.splitlines())


# ------------------------------------------------- the collection that holds it

def test_there_is_somewhere_for_an_evidence_picture_to_live():
    """The whole card was blocked here. Not on Twilio's parameter — on the
    absence of a file field anywhere in the product."""
    assert EVIDENCE_MIGRATION.exists(), (
        "no migration creates an evidence collection, so a screenshot has "
        "nowhere to be stored and `MediaUrl` has nothing to point at")
    src = migration_code()
    assert re.search(r'type:\s*"file"', src), (
        "the evidence collection has no file field — PocketBase's own file "
        "storage is the only thing here that both persists on the volume and "
        "serves bytes over https")


def test_the_picture_is_capped_and_can_only_be_a_picture():
    """The 5 GB volume filled once and took the whole product down
    (audit_retention.pb.js:3-11, backend/start.sh:6-8). An uncapped upload
    field is the same outage with a different filler."""
    src = migration_code()
    assert re.search(r"maxSize:\s*\d+", src), "an evidence image needs a byte ceiling"
    size = int(re.search(r"maxSize:\s*(\d+)", src).group(1))
    assert 0 < size <= 400_000, (
        "the ceiling must not exceed the extension's own screenshot ceiling "
        "(agent_loop.js:129) or the upload fails at a different threshold than "
        f"the capture: got {size}")
    assert "image/jpeg" in src and "mimeTypes" in src, (
        "the field must accept images only; a general file field on a public "
        "URL is a file host, not an evidence host")
    assert "maxSelect: 1" in src, "one picture per receipt, not an album"


def test_evidence_cannot_be_rewritten_or_erased_through_the_api():
    """A receipt somebody can edit is not a receipt. Update and delete stay
    superuser-only so neither a paired browser nor a signed-in account can
    re-point a share window or destroy the proof of what was done."""
    src = migration_code()
    assert re.search(r"updateRule:\s*null", src), (
        "updateRule must be null — otherwise a caller past the token gate can "
        "PATCH share_expires and mint itself a permanent public URL")
    assert re.search(r"deleteRule:\s*null", src), "deleteRule must be null"


MIGRATION_HARNESS = r"""
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const args = process.argv.slice(-2);
const scenario = JSON.parse(args[0]);
const MIGRATIONS = args[1];

const logs = [];
let up = null;
const ctx = {
  console: { log: (...p) => logs.push(p.map(String).join(' ')) },
  migrate: (u) => { up = u; },
  Collection: function (spec) {
    this.type = spec.type;
    this.name = spec.name;
    this.rawFields = (spec.fields || []).slice();
    this.listRule = spec.listRule;
    this.viewRule = spec.viewRule;
    this.createRule = spec.createRule;
    this.updateRule = spec.updateRule;
    this.deleteRule = spec.deleteRule;
    this.indexes = [];
    this.fields = {
      getByName: (n) => this.rawFields.filter((f) => f.name === n)[0] || null,
    };
  },
  Field: function (spec) { Object.assign(this, spec); },
};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(MIGRATIONS, '1700000045_evidence.js'), 'utf8'), ctx);

let stored = null;
const app = {
  save: (collection) => { stored = collection; },
  findCollectionByNameOrId: (name) => {
    if (!stored || stored.name !== name) throw new Error('no such collection');
    // WHAT DID NOT LAND. PocketBase is a Go-backed object here; a field or a
    // rule can silently fail to apply, which is the whole reason the migration
    // reads itself back (1700000044_purges_markable.js:39-47).
    const drop = scenario.dropped || '';
    const copy = Object.create(Object.getPrototypeOf(stored));
    Object.assign(copy, stored);
    copy.rawFields = stored.rawFields.slice();
    if (drop === 'image') copy.rawFields = copy.rawFields.filter((f) => f.name !== 'image');
    if (drop === 'image_type') {
      copy.rawFields = copy.rawFields.map(
        (f) => f.name === 'image' ? Object.assign({}, f, { type: 'text' }) : f);
    }
    if (drop === 'updateRule') copy.updateRule = '';
    if (drop === 'deleteRule') copy.deleteRule = '';
    copy.fields = {
      getByName: (n) => copy.rawFields.filter((f) => f.name === n)[0] || null,
    };
    return copy;
  },
  delete: () => {},
};

let threw = null;
try { up(app); } catch (err) { threw = String(err); }
process.stdout.write(JSON.stringify({
  threw: threw, logs: logs,
  saved: stored ? {
    name: stored.name, listRule: stored.listRule, viewRule: stored.viewRule,
    createRule: stored.createRule,
    updateRule: stored.updateRule === null ? 'NULL' : stored.updateRule,
    deleteRule: stored.deleteRule === null ? 'NULL' : stored.deleteRule,
    fields: stored.rawFields, indexes: stored.indexes,
  } : null,
}));
"""


def migrate(**scenario) -> dict:
    proc = subprocess.run(
        ["node", "-e", MIGRATION_HARNESS, "--", json.dumps(scenario), str(MIGRATIONS)],
        capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise AssertionError(f"harness failed: {proc.stderr[-3000:]}")
    return json.loads(proc.stdout)


def test_the_migration_runs_and_creates_what_it_says_it_does():
    """Executed, not grepped. There is no PocketBase binary in this tree, so
    this is the only place a syntax error or a misnamed field in the migration
    can be caught before it reaches a boot that fails."""
    out = migrate()
    assert out["threw"] is None, out["threw"]
    saved = out["saved"]
    assert saved and saved["name"] == "evidence", out
    image = [f for f in saved["fields"] if f["name"] == "image"]
    assert image and image[0]["type"] == "file", saved["fields"]
    assert saved["updateRule"] == "NULL" and saved["deleteRule"] == "NULL", saved
    assert saved["createRule"] == "" and saved["viewRule"] == "", saved
    assert [f["name"] for f in saved["fields"]].count("owner_ref") == 1


def test_the_migration_refuses_to_finish_when_something_did_not_land():
    """1700000044_purges_markable.js:39-47 — a rule that did not land is
    invisible until the next real request, and the request that would reveal
    THIS one is a stranger fetching somebody's screenshot.

    Driven per failure, because a readback that merely mentions a field in its
    error message reads exactly like one that checks it. Mutating the
    condition away left every source-shape version of this test green.
    """
    for dropped in ("image", "image_type", "updateRule", "deleteRule"):
        out = migrate(dropped=dropped)
        assert out["threw"], (
            f"the migration reported success with {dropped} not applied: {out}")


# ----------------------------------------------------------- the fetch gate

def test_an_evidence_url_nobody_shared_is_refused():
    """DEFAULT DENY. This is the property the whole exposure argument rests
    on: an evidence row that has never been shared has no public URL at all,
    even to somebody holding the exact path."""
    out = fetch(evidence_row())
    assert out["outcome"] == "json" and out["status"] in (403, 404), out
    assert out["saved"] == [], "an unshared fetch must not be counted as one"


def test_an_open_share_window_serves_the_picture_and_spends_a_fetch():
    """Twilio's door. It has to actually open, or the photo never reaches a
    phone and this whole host is decoration."""
    out = fetch(evidence_row(share_expires=FUTURE, fetches=0))
    assert out["outcome"] == "next", out
    assert out["saved"] and out["saved"][0]["fetches"] == 1, (
        "a public fetch must be counted, or the ceiling below bounds nothing")


def test_an_expired_share_window_is_refused():
    out = fetch(evidence_row(share_expires=PAST))
    assert out["outcome"] == "json" and out["status"] in (403, 404), out


def test_an_unparseable_share_window_is_refused_rather_than_trusted():
    """`new Date("soon").getTime()` is NaN, and `NaN <= Date.now()` is false —
    so the obvious expiry check lets garbage through. Same idiom, and the same
    trap, as workflow_guard.pb.js:160-161."""
    out = fetch(evidence_row(share_expires="soon"))
    assert out["outcome"] == "json" and out["status"] in (403, 404), out


def test_a_shared_url_dies_after_a_few_fetches():
    """Expiry alone is not enough: a leaked URL inside the window is otherwise
    an unlimited download. Twilio fetches once and retries a handful of times,
    so a small ceiling costs a real send nothing."""
    out = fetch(evidence_row(share_expires=FUTURE, fetches=99))
    assert out["outcome"] == "json" and out["status"] in (403, 404), out


def test_a_refusal_does_not_say_which_refusal_it_was():
    """An anonymous caller who can tell "no such row" from "not shared" from
    "expired" has an oracle for walking record ids. Every refusal on the
    public door answers the same way."""
    answers = {
        json.dumps(fetch(None, path="/api/files/evidence/ev0000000000001/x.jpg")["body"]),
        json.dumps(fetch(evidence_row())["body"]),
        json.dumps(fetch(evidence_row(share_expires=PAST))["body"]),
        json.dumps(fetch(evidence_row(share_expires=FUTURE, fetches=99))["body"]),
    }
    assert len(answers) == 1, f"the refusals are distinguishable: {answers}"


def test_the_gate_is_not_fooled_by_the_collection_id():
    """PocketBase serves /api/files/{collectionIdOrName}/... — matching the
    literal string "evidence" is bypassable by anyone who has read the
    collection's 15-character id, which is not a secret."""
    out = fetch(evidence_row(), key="pbc_evidence001")
    assert out["outcome"] == "json", (
        "addressing the collection by id walked straight past the gate")


def test_a_database_hiccup_closes_the_gate_rather_than_opening_it():
    """guard.pb.js:326-333 — a gate that fails open when the database hiccups
    is a gate you open by making the database hiccup."""
    out = fetch(evidence_row(share_expires=FUTURE), lookupThrows=True)
    assert out["outcome"] == "json", out


def test_a_fetch_that_cannot_be_counted_is_refused():
    """Same posture as the pair-code throttle (guard.pb.js:127-138): serving
    what nobody is counting is the hole this closes. The cost is a text that
    goes out without its picture, which is the designed fallback."""
    out = fetch(evidence_row(share_expires=FUTURE), saveFails=True)
    assert out["outcome"] == "json", out


def test_the_owner_reaches_their_own_evidence_without_any_public_window():
    """The app's door. The picture in his own app is not the picture on the
    public internet, and it must not need one to exist."""
    out = fetch(evidence_row(), auth={"id": "own1", "collection": "owners"})
    assert out["outcome"] == "next", out
    assert out["saved"] == [], (
        "the owner's own reads must not spend Twilio's fetch ceiling")


def test_another_account_cannot_read_this_owners_evidence():
    out = fetch(evidence_row(), auth={"id": "own2", "collection": "owners"})
    assert out["outcome"] == "json", out


def test_an_auth_record_that_is_not_an_account_is_not_the_owner():
    """`e.auth` is populated for ANY auth record in PocketBase 0.30.4,
    superusers included — guard.pb.js:358-366 documents exactly this."""
    out = fetch(evidence_row(owner_ref="ag01"),
                auth={"id": "ag01", "collection": "agents"})
    assert out["outcome"] == "json", out


def test_the_worker_reaches_it_with_the_service_token():
    out = fetch(evidence_row(), headers={"X-Anticipy-Token": SERVICE_TOKEN})
    assert out["outcome"] == "next", out


def test_a_wrong_service_token_is_not_a_service_token():
    out = fetch(evidence_row(), headers={"X-Anticipy-Token": "nope"})
    assert out["outcome"] == "json", out


def test_an_unset_service_token_is_not_a_credential_on_the_fetch_door():
    """`getenv` returns "" when the variable is missing and `header.get`
    returns "" when the header is absent, so the obvious comparison is
    `"" === ""` — an open door on any box where the token was never set."""
    out = fetch(evidence_row(), env={}, headers={})
    assert out["outcome"] == "json", out
    out = fetch(evidence_row(), env={}, headers={"X-Anticipy-Token": ""})
    assert out["outcome"] == "json", out


def test_no_other_collection_gets_a_public_file_url_by_accident():
    """Today no other collection has a file field. If one is ever added it
    must come and say so here rather than inheriting a public URL — which is
    precisely how an evidence host becomes a CDN."""
    out = fetch(None, key="events", path="/api/files/events/rec1/leak.jpg",
                collections=COLLECTIONS)
    assert out["outcome"] == "json", out


def test_paths_that_are_not_file_requests_are_left_alone():
    """The gate must not become a second, accidental authorization layer over
    the whole API."""
    out = drive(handler="use", path="/api/collections/jobs/records",
                collections=COLLECTIONS, rows=[])
    assert out["outcome"] == "next", out


# ------------------------------------------------------------- the share mint

def share(**over) -> dict:
    scenario = {
        "handler": "share",
        "method": "POST",
        "path": "/evidence/share",
        "collections": COLLECTIONS,
        "rows": [evidence_row()],
        "headers": {"X-Anticipy-Token": SERVICE_TOKEN},
        "body": {"id": "ev0000000000001"},
    }
    scenario.update(over)
    return drive(**scenario)


def test_only_the_worker_may_open_a_public_window():
    out = share(headers={})
    assert out["outcome"] == "json" and out["status"] == 403, out
    out = share(headers={"X-Anticipy-Token": "nope"})
    assert out["outcome"] == "json" and out["status"] == 403, out


def test_an_unset_service_token_does_not_mean_everybody_is_the_worker():
    """`getenv` returning "" compared against a missing header is "" === "",
    which is how a token check becomes an open door on a misconfigured box."""
    out = share(env={"ANTICIPY_PUBLIC_URL": "https://backend.example"}, headers={})
    assert out["outcome"] == "json" and out["status"] == 403, out


def test_opening_a_window_returns_the_url_twilio_will_fetch():
    out = share()
    assert out["outcome"] == "json" and out["status"] == 200, out
    body = out["body"]
    assert body["ok"] is True, body
    assert body["url"].startswith("https://backend.example/api/files/evidence/"), body
    assert "ev0000000000001" in body["url"] and "shot_a1b2c3d4e5.jpg" in body["url"], body
    assert body["expires"], "the caller must be told when the window shuts"
    stamped = out["saved"][-1]
    assert stamped["share_expires"], "the window must actually be written down"


def test_re_sharing_a_spent_picture_hands_back_a_fresh_ceiling():
    """Without this, the second text about the same errand opens a window
    nothing can come through — the fetch count is already at the limit — and
    the photo goes missing for a reason no log names."""
    out = share(rows=[evidence_row(fetches=99)])
    assert out["body"]["ok"] is True, out
    assert out["saved"][-1]["fetches"] == 0, (
        f"a re-shared picture kept its spent ceiling: {out['saved'][-1]}")


def test_a_missing_picture_is_an_answer_not_a_broken_link():
    """WHAT HAPPENS WHEN IT IS GONE. An expired, swept or never-uploaded
    picture must hand the caller an explicit "no photo" so the text goes out
    with its words. A 404 handed to Twilio as a MediaUrl fails the whole
    message — the person gets nothing at all instead of the sentence."""
    for scenario in ({"rows": []},
                     {"rows": [evidence_row(image="")]},
                     {"body": {"id": ""}}):
        out = share(**scenario)
        assert out["status"] == 200, out
        assert out["body"]["ok"] is False, out
        assert not out["body"].get("url"), (
            "an absent picture must not yield a URL that will 404 at Twilio")
        assert out["body"].get("reason"), "and it must say which absence it was"


def test_without_a_public_base_url_no_link_is_invented():
    out = share(env={"ANTICIPY_SERVICE_TOKEN": SERVICE_TOKEN})
    assert out["body"]["ok"] is False and not out["body"].get("url"), out


# ----------------------------------------------------------------- retention

def test_evidence_trims_itself_on_every_write():
    """Two defences, because one was not enough last time
    (audit_retention.pb.js:13-18). The volume filling is not a hypothetical
    here: it is a recorded outage, and PocketBase's scheduled backup zips
    pb_data — storage included — onto the same volume and keeps two
    (1700000037_backup_footprint.js), so every stored byte is charged three
    times at peak."""
    rows = [evidence_row(id=f"ev{i:013d}", created=f"2026-08-{(i % 28) + 1:02d}T00:00:00Z")
            for i in range(200)]
    out = drive(handler="sweep", rows=rows, collections=COLLECTIONS,
                newRecord={"collection": "evidence", "id": "evNEW",
                           "owner_ref": "own1"})
    assert out["sweepCollection"] == "evidence", (
        "the sweep must be bound to the evidence collection or it runs on "
        f"every write in the database: {out['sweepCollection']!r}")
    assert out["deleted"], "nothing was swept, so the cap is decorative"


def test_one_owner_cannot_fill_the_table_under_the_global_cap():
    """The per-owner cap has to bite on its own. Thirty-five rows in total is
    comfortably under the whole-table ceiling, so if only the global sweep
    runs, nothing is deleted and one account's screenshots accumulate
    indefinitely — which is a privacy problem before it is a disk one."""
    rows = ([evidence_row(id=f"eva{i:012d}", owner_ref="own1",
                          created=f"2026-08-{(i % 28) + 1:02d}T00:00:00Z")
             for i in range(30)]
            + [evidence_row(id=f"evb{i:012d}", owner_ref="own2",
                            created="2026-08-01T00:00:00Z") for i in range(5)])
    out = drive(handler="sweep", rows=rows, collections=COLLECTIONS,
                newRecord={"collection": "evidence", "id": "evNEW",
                           "owner_ref": "own1"})
    assert out["deleted"], "the per-owner cap never fired"
    assert all(d.startswith("eva") for d in out["deleted"]), (
        f"the sweep took another owner's rows: {out['deleted']}")


def test_a_failed_sweep_never_breaks_the_write_that_triggered_it():
    out = drive(handler="sweep", rows=[evidence_row()], collections=COLLECTIONS,
                filterThrows=True,
                newRecord={"collection": "evidence", "id": "evNEW",
                           "owner_ref": "own1"})
    assert out["threw"] is None
    assert out["outcome"] == "next", (
        "housekeeping that fails must still let the record through")


# ------------------------------------------------------------------- erasure

def test_deleting_an_account_deletes_its_evidence_pictures():
    """The privacy page promises erasure and account_delete.pb.js performs it
    from a list that lives inside the handler. A collection missing from that
    list is PII with no cascade and nothing else that would ever remove it —
    which is the exact sentence account_delete.pb.js:63-66 writes about the
    audit ledger."""
    src = (HOOKS / "account_delete.pb.js").read_text()
    handler = src.split('routerAdd("POST", "/me/delete"', 1)[1]
    tables = handler.split("const OWNER_TABLES", 1)[1].split("];", 1)[0]
    assert '"evidence"' in tables, (
        "evidence rows carry owner_ref and a stored image file; if /me/delete "
        "does not name the collection, a deleted account's screenshots stay "
        "on the volume forever")


# ------------------------------------------------------- the way bytes get in

def guard(**over) -> dict:
    scenario = {
        "hook": "guard.pb.js",
        "handler": "use",
        "method": "POST",
        "path": "/api/collections/evidence/records",
        "collections": COLLECTIONS,
        "rows": [
            {"collection": "agents", "id": "agrec1", "agent_id": "AG1",
             "agent_token": "t" * 48, "owner_ref": "own1", "paired": True},
        ],
        "headers": {"X-Anticipy-Agent-ID": "AG1", "X-Anticipy-Agent-Token": "t" * 48},
        "body": {"owner_ref": "own1", "job": "job0000000000001"},
    }
    scenario.update(over)
    return drive(**scenario)


def test_a_paired_browser_may_deposit_evidence_for_its_own_owner():
    """The extension is the only thing in the system that HOLDS a screenshot.
    Without this branch the bytes can never get in, and the host is a room
    with no door."""
    out = guard()
    assert out["outcome"] == "next", out


def test_a_paired_browser_cannot_deposit_evidence_against_another_owner():
    out = guard(body={"owner_ref": "own2", "job": "job0000000000001"})
    assert out["outcome"] == "json" and out["status"] == 403, out


def test_the_signed_in_owner_can_read_their_own_evidence_rows():
    """The app has to find the row before it can render the picture."""
    out = guard(method="GET", path="/api/collections/evidence/records",
                headers={}, body={},
                auth={"id": "own1", "collection": "owners"},
                query={"filter": 'owner_ref="own1"'})
    assert out["outcome"] == "next", out


@pytest.mark.parametrize("path", [
    "/api/collections/evidence/records/ev0000000000001",
])
def test_a_paired_browser_may_not_edit_evidence_after_depositing_it(path):
    out = guard(method="PATCH", path=path,
                body={"share_expires": "2099-01-01T00:00:00Z"})
    assert out["outcome"] == "json", (
        "a browser that can PATCH an evidence row can mint itself a public "
        "URL that never expires")


# --------------------------------------------- the hook survives its own runtime

def test_every_constant_the_gate_needs_is_declared_inside_the_handler():
    """Proven, not asserted: every drive() above re-runs the captured handler
    source in a FRESH context with only PocketBase's globals, and asserts it
    did not throw. This test states the rule so the reason survives a
    refactor."""
    src = EVIDENCE_HOOK.read_text()
    assert "routerUse" in src and "routerAdd" in src
    assert "not in scope" in src or "isolated" in src or "own execution context" in src, (
        "the file must carry the scope warning the other hooks carry; it has "
        "cost this repository a whole feature once")
