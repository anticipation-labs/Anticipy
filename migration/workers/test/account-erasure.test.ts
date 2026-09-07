/** Real account handler + real schema/SQLite. No provider or network calls.
 * Run: node --experimental-strip-types migration/workers/test/account-erasure.test.ts
 * Inspect surviving state independently; do not infer erasure from HTTP 200.
 */
import assert from "node:assert/strict";
import { FakeD1, asD1 } from "./fake-d1.ts";
import { issueToken } from "../src/api/auth.ts";
import { accountDelete, ACCOUNT_TABLES } from "../src/routes/account_delete.ts";
import { ComposioConnections } from "../src/connections/provider.ts";

let failures = 0;
let passes = 0;
async function check(name: string, fn: () => Promise<void>) {
  try { await fn(); passes++; console.log("PASS " + name); }
  catch (error) { failures++; console.error("FAIL " + name + ": " + (error as Error).message); }
}
const A = "auditowner00001";
const B = "auditowner00002";
function rig(legacy = "") {
  const db = new FakeD1();
  for (const ref of [A, B]) db.db.prepare(
    "INSERT INTO owners (id,email,tokenKey,legacy_uuid) VALUES (?,?,?,?)",
  ).run(ref, ref + "@anticipy-test.invalid", "key-" + ref, ref === A ? legacy : "");
  const objects = new Set<string>();
  const env = {
    DB: asD1(db), ANTICIPY_AUTH_SECRET: "audit-erasure-test-secret",
    EVIDENCE: { async delete(keys: string | string[]) {
      for (const key of typeof keys === "string" ? [keys] : keys) objects.delete(key);
    } },
  };
  return { db, env, objects };
}
async function erase(r: ReturnType<typeof rig>, provider?: Pick<ComposioConnections, "connections" | "disconnect">) {
  const token = await issueToken(r.env, A, "key-" + A);
  return accountDelete(new Request("https://api.anticipy.ai/me/delete", {
    method: "POST", headers: { Authorization: token, "content-type": "application/json" },
    body: JSON.stringify({ confirm: "delete" }),
  }), r.env, provider);
}

await check("the deployed purge ledger without synthetic autodates supports cleanup", async () => {
  const r = rig();
  r.db.db.exec("ALTER TABLE purges DROP COLUMN created; ALTER TABLE purges DROP COLUMN updated;");
  assert.equal((await erase(r)).status, 200);
  assert.equal(r.db.rows("SELECT * FROM owners WHERE id = ?", A).length, 0);
  assert.equal(r.db.rows("SELECT * FROM purges WHERE owner_ref = ?", A).length, 1);
});

await check("deletion removes all local connection state and preserves another owner", async () => {
  const r = rig();
  for (const ref of [A, B]) {
    r.db.db.prepare("INSERT INTO connections (connected_account_id,user_id,toolkit,status) VALUES (?,?,?,'connected')")
      .run("ca_" + ref, ref, "gmail");
    r.db.db.prepare("INSERT INTO connect_links (token_handle,user_id,toolkit,expires_at) VALUES (?,?,?,?)")
      .run((ref === A ? "a" : "b").repeat(64), ref, "gmail", Date.now() + 60000);
    r.db.db.prepare("INSERT INTO app_usage_signals (user_id,toolkit,source) VALUES (?,?,'said')")
      .run(ref, "gmail");
    r.db.db.prepare("INSERT INTO connect_nudges (user_id,toolkit,state) VALUES (?,?,'never_asked')")
      .run(ref, "gmail");
    r.db.db.prepare("INSERT INTO connect_codes (id,token_handle,user_id,code_hash,expires_at,created_at) VALUES (?,?,?,?,?,?)")
      .run("code-" + ref, (ref === A ? "a" : "b").repeat(64), ref, "c".repeat(64), Date.now() + 60000, Date.now());
  }
  const response = await erase(r, {
    async connections() { return []; },
    async disconnect() { throw new Error("no remote connection to delete"); },
  });
  assert.equal(response.status, 200);
  for (const table of ["connections", "connect_links", "connect_codes", "app_usage_signals", "connect_nudges"]) {
    assert.equal(r.db.rows(`SELECT * FROM ${table} WHERE user_id = ?`, A).length, 0, table + " retained deleted owner");
    assert.equal(r.db.rows(`SELECT * FROM ${table} WHERE user_id = ?`, B).length, 1, table + " lost another owner");
  }
});

await check("password reset material is erased for exactly this account", async () => {
  const r = rig();
  for (const ref of [A, B]) r.db.db.prepare(
    "INSERT INTO password_resets (id,owner,code_hash,expires) VALUES (?,?,?,?)",
  ).run("reset-" + ref, ref, "hash-" + ref, "2027-01-01T00:00:00Z");
  assert.equal((await erase(r)).status, 200);
  assert.equal(r.db.rows("SELECT * FROM password_resets WHERE owner = ?", A).length, 0);
  assert.equal(r.db.rows("SELECT * FROM password_resets WHERE owner = ?", B).length, 1);
});

await check("a claimed legacy ID never authorizes deleting another owner's profile", async () => {
  const r = rig(B);
  for (const ref of [A, B]) r.db.db.prepare(
    "INSERT INTO owner_profile (id,owner_ref,owner_id,name) VALUES (?,?,?,?)",
  ).run("profile-" + ref, ref, ref === A ? "legacy-self" : B, ref);
  assert.equal((await erase(r)).status, 200);
  assert.equal(r.db.rows("SELECT * FROM owner_profile WHERE owner_ref = ?", A).length, 0);
  assert.equal(r.db.rows("SELECT * FROM owner_profile WHERE owner_ref = ?", B).length, 1,
    "another account's authoritative owner_ref must outrank client-supplied legacy_uuid");
});

await check("a claimed legacy ID never authorizes deleting another owner's job", async () => {
  const r = rig(B);
  for (const ref of [A, B]) r.db.db.prepare(
    "INSERT INTO jobs (id,owner_ref,owner,goal,status) VALUES (?,?,?,?,?)",
  ).run("job-" + ref, ref, ref === A ? "legacy-self" : B, "Read my calendar", "queued");
  assert.equal((await erase(r)).status, 200);
  assert.equal(r.db.rows("SELECT * FROM jobs WHERE owner_ref = ?", A).length, 0);
  assert.equal(r.db.rows("SELECT * FROM jobs WHERE owner_ref = ?", B).length, 1);
});

await check("erasure deletes evidence bytes as well as rows for exactly this owner", async () => {
  const r = rig();
  for (const ref of [A, B]) {
    r.db.db.prepare("INSERT INTO evidence (id,owner_ref,image,job) VALUES (?,?,?,?)")
      .run("receipt-" + ref, ref, "private.png", "job-" + ref);
    r.objects.add("evidence/receipt-" + ref + "/private.png");
  }
  assert.equal((await erase(r)).status, 200);
  assert.equal(r.objects.has("evidence/receipt-" + A + "/private.png"), false);
  assert.equal(r.objects.has("evidence/receipt-" + B + "/private.png"), true);
  assert.equal(r.db.rows("SELECT * FROM evidence WHERE owner_ref = ?", B).length, 1);
});

await check("the real schema has no omitted product-owned table", async () => {
  const r = rig();
  const covered = new Set<string>(ACCOUNT_TABLES.map(([table]) => table));
  for (const { name } of r.db.rows<{name: string}>("SELECT name FROM sqlite_master WHERE type = 'table'")) {
    // Internal workspace people are a separate identity system. purges is the
    // intentional tombstone/outbox that must survive account deletion.
    if (name.startsWith("internal_") || name === "purges") continue;
    const columns = r.db.rows<{name: string}>(`PRAGMA table_info("${name}")`).map((c) => c.name);
    if (columns.some((c) => ["owner_ref", "user_id", "owner"].includes(c))) {
      assert.ok(covered.has(name), "erasure omitted schema table " + name);
    }
  }
});

await check("provider failure keeps the account, local handles and retry path", async () => {
  const r = rig();
  r.db.db.prepare("INSERT INTO connections (connected_account_id,user_id,toolkit,status) VALUES (?,?,?,'connected')")
    .run("ca_retry", A, "gmail");
  const response = await erase(r, {
    async connections() { throw new Error("provider timeout"); },
    async disconnect() { throw new Error("must not disconnect"); },
  });
  assert.equal(response.status, 503);
  assert.equal(r.db.rows("SELECT id FROM owners WHERE id = ?", A).length, 1);
  assert.equal(r.db.rows("SELECT * FROM connections WHERE user_id = ?", A).length, 1);
  assert.equal(r.db.rows("SELECT * FROM purges").length, 1, "the write fence survives provider failure");
});

await check("unconfigured provider cannot turn cached connections into a successful erase", async () => {
  const r = rig();
  r.db.db.prepare("INSERT INTO connections (connected_account_id,user_id,toolkit,status) VALUES (?,?,?,'connected')")
    .run("ca_retry", A, "gmail");
  assert.equal((await erase(r)).status, 503);
  assert.equal(r.db.rows("SELECT id FROM owners WHERE id = ?", A).length, 1);
});

await check("failed bucket deletion preserves the only metadata handle", async () => {
  const r = rig();
  r.db.db.prepare("INSERT INTO evidence (id,owner_ref,image,job) VALUES (?,?,?,?)")
    .run("receipt-retry", A, "private.png", "job-retry");
  r.env.EVIDENCE.delete = async () => { throw new Error("R2 unavailable"); };
  assert.equal((await erase(r)).status, 503);
  assert.equal(r.db.rows("SELECT * FROM evidence WHERE owner_ref = ?", A).length, 1);
  assert.equal(r.db.rows("SELECT id FROM owners WHERE id = ?", A).length, 1);
});

await check("a failed final account delete preserves rows and keeps the retry fence", async () => {
  const r = rig();
  r.db.db.prepare("INSERT INTO owner_profile (id,owner_ref,owner_id,name) VALUES (?,?,?,?)")
    .run("profile-retry", A, A, "Synthetic owner");
  r.db.failOn = (sql) => sql === "DELETE FROM owners WHERE id = ?";
  assert.equal((await erase(r)).status, 409);
  assert.equal(r.db.rows("SELECT * FROM owner_profile WHERE owner_ref = ?", A).length, 1);
  assert.equal(r.db.rows("SELECT * FROM purges").length, 1);
  r.db.failOn = null;
  assert.equal((await erase(r)).status, 200);
  assert.equal(r.db.rows("SELECT * FROM purges WHERE owner_ref = ?", A).length, 1);
});

await check("an unclaimed row does not become deletable through a claimed legacy UUID", async () => {
  const r = rig("historical-private-id");
  r.db.db.prepare("INSERT INTO jobs (id,owner_ref,owner,goal,status) VALUES (?,?,?,?,?)")
    .run("unclaimed", "", "historical-private-id", "Private historical job", "queued");
  assert.equal((await erase(r)).status, 200);
  assert.equal(r.db.rows("SELECT * FROM jobs WHERE id = 'unclaimed'").length, 1);
});

await check("writes racing picture cleanup cannot create untracked evidence", async () => {
  const r = rig();
  r.db.db.prepare("INSERT INTO evidence (id,owner_ref,image,job) VALUES (?,?,?,?)")
    .run("receipt-initial", A, "initial.png", "job-initial");
  r.objects.add("evidence/receipt-initial/initial.png");
  let refused = false;
  const remove = r.env.EVIDENCE.delete;
  r.env.EVIDENCE.delete = async (keys) => {
    await remove(keys);
    try {
      r.db.db.prepare("INSERT INTO evidence (id,owner_ref,image,job) VALUES (?,?,?,?)")
        .run("receipt-racing", A, "racing.png", "job-racing");
      r.objects.add("evidence/receipt-racing/racing.png");
    } catch (error) {
      assert.match(String(error), /ACCOUNT_ERASURE_IN_PROGRESS/);
      refused = true;
    }
  };
  assert.equal((await erase(r)).status, 200);
  assert.equal(refused, true, "an in-flight writer crossed the erasure boundary");
  assert.equal(r.objects.size, 0, "metadata cleanup lost a late picture's handle");
});

await check("a completed deletion cannot be followed by stale-account writes", async () => {
  const r = rig();
  assert.equal((await erase(r)).status, 200);
  assert.throws(() => r.db.db.prepare("INSERT INTO events (id,owner_ref,kind,text,device_id) VALUES (?,?,?,?,?)")
    .run("late-event", A, "transcript", "stale writer", "audit-device"), /ACCOUNT_ERASURE_IN_PROGRESS/);
  r.db.db.prepare("INSERT INTO events (id,owner_ref,kind,text,device_id) VALUES (?,?,?,?,?)")
    .run("other-event", B, "transcript", "another owner survives", "audit-device");
  assert.equal(r.db.rows("SELECT * FROM events WHERE owner_ref = ?", B).length, 1);
});

await check("missing fence migration refuses cleanup before external deletion", async () => {
  const r = rig();
  r.db.db.exec("DROP TRIGGER erasure_fence_events_insert");
  let providerCalled = false;
  const response = await erase(r, {
    async connections() { providerCalled = true; return []; },
    async disconnect() { throw new Error("unreachable"); },
  });
  assert.equal(response.status, 503);
  assert.equal(providerCalled, false);
  assert.equal(r.db.rows("SELECT * FROM purges").length, 0);
  assert.equal(r.db.rows("SELECT id FROM owners WHERE id = ?", A).length, 1);
});

await check("fence blocks ownership reassignment and canonical ID resurrection", async () => {
  const r = rig();
  r.db.db.prepare("INSERT INTO owner_profile (id,owner_ref,owner_id) VALUES (?,?,?)")
    .run("moving-profile", A, A);
  r.db.failOn = sql => sql === "DELETE FROM owners WHERE id = ?";
  assert.equal((await erase(r)).status, 409);
  assert.throws(() => r.db.db.prepare("UPDATE owner_profile SET owner_ref = ? WHERE id = ?")
    .run(B, "moving-profile"), /ACCOUNT_ERASURE_IN_PROGRESS/);
  r.db.failOn = null;
  assert.equal((await erase(r)).status, 200);
  assert.throws(() => r.db.db.prepare("INSERT INTO owners (id,email,tokenKey) VALUES (?,?,?)")
    .run(A, "recreated@anticipy-test.invalid", "new-key"), /ACCOUNT_ERASURE_IN_PROGRESS/);
});

console.log(`account erasure: ${passes} passed, ${failures} failed`);
if (failures) process.exit(1);
