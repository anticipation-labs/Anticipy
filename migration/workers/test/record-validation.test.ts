import assert from "node:assert/strict";
import { FakeD1, asD1 } from "./fake-d1.ts";
import { create, update, type RecordsRequest } from "../src/pb/records.ts";
import { COLLECTIONS } from "../src/pb/schema.ts";

let failures = 0;
async function check(name: string, test: () => Promise<void>) {
  try { await test(); console.log("PASS " + name); }
  catch (error) { failures++; console.error("FAIL " + name + ": " + (error as Error).message); }
}
function req(name: string, body: Record<string, unknown>, recordId?: string): RecordsRequest {
  return { collection: COLLECTIONS[name], body, recordId: recordId || null,
    method: recordId ? "PATCH" : "POST", principal: { kind: "service" },
    url: new URL("https://local.invalid/api/collections/" + name + "/records") };
}

await check("missing required record fields produce validation responses, not exceptions", async () => {
  for (const [collection, column] of [["agents", "agent_id"], ["events", "device_id"], ["jobs", "goal"], ["owner_profile", "owner_id"], ["segments", "status"]]) {
    const db = new FakeD1();
    const response = await create({ DB: asD1(db) }, req(collection, {}));
    assert.equal(response.status, 400, collection);
    const body = await response.json() as { data: Record<string, { code: string }> };
    assert.equal(body.data[column].code, "validation_required", collection);
    assert.equal(db.rows(`SELECT * FROM ${collection}`).length, 0);
  }
});

await check("invalid PATCH and uniqueness collisions leave the original records intact", async () => {
  const db = new FakeD1();
  db.db.prepare("INSERT INTO agents (id,agent_id,pair_code) VALUES (?,?,?)").run("auditagent00001", "browser-one", "123456");
  db.db.prepare("INSERT INTO agents (id,agent_id,pair_code) VALUES (?,?,?)").run("auditagent00002", "browser-two", "654321");
  for (const body of [{ agent_id: "" }, { agent_id: "browser-two" }]) {
    const response = await update({ DB: asD1(db) }, req("agents", body, "auditagent00001"));
    assert.equal(response.status, 400);
    assert.equal(db.rows<{ agent_id: string }>("SELECT agent_id FROM agents WHERE id = 'auditagent00001'")[0].agent_id, "browser-one");
  }
});

await check("anonymous signups cannot select a previous account's canonical ID", async () => {
  const db = new FakeD1();
  const request = req("owners", { id: "oldowner0000001", email: "new@anticipy-test.invalid", password: "test-password", passwordConfirm: "test-password" });
  request.principal = { kind: "anonymous" };
  const response = await create({ DB: asD1(db) }, request);
  assert.equal(response.status, 400);
  assert.equal(db.rows("SELECT * FROM owners").length, 0);
});

await check("a database outage remains an infrastructure failure", async () => {
  const db = new FakeD1();
  db.failOn = (sql) => sql.startsWith("INSERT");
  await assert.rejects(create({ DB: asD1(db) }, req("agents", { agent_id: "browser-one", pair_code: "123456" })));
});

if (failures) process.exit(1);
