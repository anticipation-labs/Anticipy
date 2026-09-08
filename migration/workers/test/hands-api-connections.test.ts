/** The brain connection read, real handler and scoped SQL over local SQLite. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { handsApiConnections, HANDS_API_CONNECTIONS_PATH } from "../src/routes/hands_api_connections.ts";
import { createD1Store, forgetLiveColumns, type StoredConnection } from "../src/connections/store.ts";
import { FakeD1, asD1 } from "./fake-d1.ts";
import worker, { type Env } from "../src/index.ts";

const OWNER = "owner0000000001";
const OTHER = "owner0000000002";
const TOKEN = "local-connections-test-service-token";
let passed = 0;

async function check(name: string, fn: () => Promise<void> | void) {
  try { await fn(); passed++; }
  catch (error) { throw new Error(name, { cause: error }); }
}

function request(query = `owner=${OWNER}`, headers: Record<string, string> = { "X-Anticipy-Token": TOKEN }, method = "GET") {
  return new Request(`https://api.example${HANDS_API_CONNECTIONS_PATH}?${query}`, { method, headers });
}

async function rig() {
  const db = new FakeD1();
  const env = { DB: asD1(db), ANTICIPY_SERVICE_TOKEN: TOKEN };
  forgetLiveColumns(env);
  const store = createD1Store(env);
  await store.putConnection({
    user_id: OWNER, toolkit: "test_mail", connected_account_id: "ca_owner_private_id",
    alias: "work", status: "connected", writes_enabled: true,
    connected_at: 1, last_used_at: 2,
  } as StoredConnection);
  await store.putConnection({
    user_id: OTHER, toolkit: "test_notes", connected_account_id: "ca_other_private_id",
    alias: "personal", status: "needs_reconnect", writes_enabled: false,
    connected_at: 1, last_used_at: null,
  } as StoredConnection);
  db.log.length = 0;
  return { db, env, store };
}

for (const headers of [{}, { Authorization: "Bearer owner-session" }, { "X-Anticipy-Worker": "1" },
  { "X-Anticipy-Token": TOKEN.slice(1) }, { "X-Anticipy-Token": TOKEN.replace("local", "xxxxx") }]) {
  await check("authentication precedes all database access", async () => {
    const { db, env } = await rig();
    const res = await handsApiConnections(request(undefined, headers), env);
    assert.equal(res.status, 401);
    assert.deepEqual(db.log, []);
    assert.equal((await res.json() as { ok: boolean }).ok, false);
  });
}

await check("unset server token fails closed", async () => {
  const { db, env } = await rig();
  assert.equal((await handsApiConnections(request(), { ...env, ANTICIPY_SERVICE_TOKEN: "" })).status, 401);
  assert.deepEqual(db.log, []);
});

for (const method of ["POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]) {
  await check(`${method} cannot read or mutate connections`, async () => {
    const { db, env } = await rig();
    const res = await handsApiConnections(request(undefined, undefined, method), env);
    assert.equal(res.status, 405);
    assert.equal(res.headers.get("allow"), "GET");
    assert.deepEqual(db.log, []);
  });
}

for (const query of ["", "owner=", "owner=Omar", "owner=person%40example.com", "owner=%27%20OR%201%3D1--",
  `owner=${OWNER}&owner=${OTHER}`, `owner=${OWNER}&user_id=${OTHER}`, `owner=${OWNER}&filter=user_id%3D%22${OTHER}%22`]) {
  await check("ambiguous, alternate or invalid owner refused before SQL", async () => {
    const { db, env } = await rig();
    const res = await handsApiConnections(request(query), env);
    assert.equal(res.status, 400);
    assert.deepEqual(db.log, []);
  });
}

await check("owner one sees only its four planning fields", async () => {
  const { db, env } = await rig();
  const res = await handsApiConnections(request(), env);
  assert.equal(res.status, 200);
  assert.equal(res.headers.get("cache-control"), "no-store");
  assert.deepEqual(await res.json(), { ok: true, owner: OWNER, items: [
    { toolkit: "test_mail", alias: "work", status: "connected", writes_enabled: true },
  ] });
  assert.ok(db.log.some(sql => sql.includes('WHERE "user_id" = ?1')));
  assert.ok(db.log.every(sql => /^SELECT\b/.test(sql.trim())));
});

await check("owner two is scoped independently", async () => {
  const { env } = await rig();
  const res = await handsApiConnections(request(`owner=${OTHER}`), env);
  assert.deepEqual(await res.json(), { ok: true, owner: OTHER, items: [
    { toolkit: "test_notes", alias: "personal", status: "needs_reconnect", writes_enabled: false },
  ] });
});

await check("a successful empty read carries its owner", async () => {
  const { env } = await rig();
  const res = await handsApiConnections(request("owner=owner0000000003"), env);
  assert.deepEqual(await res.json(), { ok: true, owner: "owner0000000003", items: [] });
});

await check("database failure is unknown with no storage detail disclosed", async () => {
  const { db, env } = await rig();
  db.failOn = () => { throw new Error(`private storage detail for ${OTHER}`); };
  const res = await handsApiConnections(request(), env);
  assert.equal(res.status, 503);
  assert.deepEqual(await res.json(), { ok: false, message: "connections could not be read" });
});

await check("missing schema cannot masquerade as no connected apps", async () => {
  const { db, env } = await rig();
  db.db.exec("DROP TABLE connections");
  forgetLiveColumns(env);
  assert.equal((await handsApiConnections(request(), env)).status, 503);
});

await check("the store refuses even a database returning another owner's row", async () => {
  const { db, env } = await rig();
  const prepare = db.prepare.bind(db);
  db.prepare = sql => {
    const statement = prepare(sql);
    if (sql.startsWith('SELECT * FROM "connections"')) {
      const bind = statement.bind.bind(statement);
      statement.bind = (...values) => {
        const bound = bind(...values);
        bound.all = async () => ({
          results: db.rows('SELECT * FROM "connections"'), success: true,
          meta: { changes: 0, last_row_id: 0, rows_read: 2, rows_written: 0, duration: 0 },
        }) as never;
        return bound;
      };
    }
    return statement;
  };
  const res = await handsApiConnections(request(), env);
  assert.equal(res.status, 503);
  assert.deepEqual(await res.json(), { ok: false, message: "connections could not be read" });
});

await check("the read does not truncate an owner's connections to a records page", async () => {
  const { env, store } = await rig();
  for (let i = 0; i < 105; i++) {
    await store.putConnection({ user_id: OWNER, toolkit: `test_app_${i}`, connected_account_id: `ca_local_${i}`,
      alias: null, status: "connected", writes_enabled: false, connected_at: 1, last_used_at: null } as StoredConnection);
  }
  const res = await handsApiConnections(request(), env);
  const body = await res.json() as { items: Array<{ toolkit: string }> };
  assert.equal(body.items.length, 106);
  assert.ok(body.items.some(item => item.toolkit === "test_app_104"));
});

await check("Worker entry point and brain name the same route", () => {
  const source = readFileSync(new URL("../src/index.ts", import.meta.url), "utf8");
  assert.equal(source.split("if (path === HANDS_API_CONNECTIONS_PATH)").length - 1, 1);
  assert.ok(source.includes("return handsApiConnections(request, env);"));
  const brain = readFileSync(new URL("../../../brain/hands.py", import.meta.url), "utf8");
  assert.ok(brain.includes(`API_HAND_CONNECTIONS_PATH = "${HANDS_API_CONNECTIONS_PATH}"`));
  assert.ok(!brain.includes("/api/collections/connections/records"));
});

await check("the actual Worker dispatcher reaches the service route", async () => {
  const { env } = await rig();
  const res = await worker.fetch(request(), env as Env, {} as ExecutionContext);
  assert.equal(res.status, 200);
  assert.deepEqual(await res.json(), { ok: true, owner: OWNER, items: [
    { toolkit: "test_mail", alias: "work", status: "connected", writes_enabled: true },
  ] });
  const unauthenticated = await worker.fetch(request(undefined, {}), env as Env, {} as ExecutionContext);
  assert.equal(unauthenticated.status, 401);
  const mutation = await worker.fetch(request(undefined, undefined, "POST"), env as Env, {} as ExecutionContext);
  assert.equal(mutation.status, 405);
});

console.log(`hands-api-connections: ${passed} checks passed`);
