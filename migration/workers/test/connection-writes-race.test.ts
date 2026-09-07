import assert from "node:assert/strict";
import { FakeD1, asD1 } from "./fake-d1.ts";
import { issueToken } from "../src/pb/auth.ts";
import { createD1Store } from "../src/connections/store.ts";
import { connectionsApiRoute, type ConnectionsApiDeps } from "../src/routes/connections_api.ts";

const OWNER = "auditowner00001";
let failed = 0;
async function check(name: string, test: () => Promise<void>) {
  try { await test(); console.log("PASS " + name); }
  catch (error) { failed++; console.error("FAIL " + name + ": " + (error as Error).message); }
}
async function rig() {
  const db = new FakeD1();
  db.db.prepare("INSERT INTO owners (id,email,tokenKey) VALUES (?,?,?)").run(OWNER, "race@anticipy-test.invalid", "test-key");
  const env = { DB: asD1(db), ANTICIPY_AUTH_SECRET: "test-secret" };
  const store = createD1Store(env);
  for (const id of ["ca_one", "ca_two"]) {
    await store.putConnection({ user_id: OWNER as never, connected_account_id: id,
      toolkit: "calendar", alias: null, status: "connected", writes_enabled: false, last_used_at: null });
  }
  const token = await issueToken(env, OWNER, "test-key");
  const request = () => new Request("https://local.invalid/me/connections/writes", {
    method: "POST", headers: { Authorization: token, "Content-Type": "application/json" },
    body: JSON.stringify({ rows: ["ca_one", "ca_two"].map(id => ({
      connected_account_id: id, toolkit: "calendar", writes_enabled: true,
    })) }),
  });
  return { db, env, store, request };
}

await check("disconnect after validation cannot be resurrected by a write toggle", async () => {
  const r = await rig();
  const read = r.store.readConnection;
  r.store.readConnection = async (owner, id) => {
    const found = await read(owner, id);
    if (id === "ca_two") await r.store.deleteConnection(owner, id);
    return found;
  };
  const response = await connectionsApiRoute(r.request(), r.env, { store: r.store } as ConnectionsApiDeps);
  assert.equal(response.status, 409);
  assert.equal(r.db.rows("SELECT * FROM connections WHERE connected_account_id = 'ca_two'").length, 0);
  assert.equal(r.db.rows<{ writes_enabled: number }>("SELECT writes_enabled FROM connections WHERE connected_account_id = 'ca_one'")[0].writes_enabled, 0,
    "a stale batch must not be applied in part");
});

await check("a concurrent expiry is preserved while changing only write permission", async () => {
  const r = await rig();
  const read = r.store.readConnection;
  r.store.readConnection = async (owner, id) => {
    const found = await read(owner, id);
    if (id === "ca_two") r.db.db.prepare("UPDATE connections SET status='needs_reconnect', last_used_at=123 WHERE connected_account_id='ca_one'").run();
    return found;
  };
  assert.equal((await connectionsApiRoute(r.request(), r.env, { store: r.store } as ConnectionsApiDeps)).status, 200);
  const row = r.db.rows<{ status: string; last_used_at: number; writes_enabled: number }>("SELECT * FROM connections WHERE connected_account_id='ca_one'")[0];
  assert.equal(row.status, "needs_reconnect");
  assert.equal(row.last_used_at, 123);
  assert.equal(row.writes_enabled, 1);
});

if (failed) process.exit(1);
