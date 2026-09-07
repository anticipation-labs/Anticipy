/** Real auth + records handler + real SQLite: bypass and malformed-wire regressions. */
import assert from "node:assert/strict";
import { FakeD1, asD1 } from "./fake-d1.ts";
import { issueToken, verifyToken } from "../src/api/auth.ts";
import { remove } from "../src/api/records.ts";
import { COLLECTIONS } from "../src/api/schema.ts";
import type { RecordsRequest } from "../src/api/records.ts";

const ref = "auditowner00001";
let failed = 0;
for (const [name, test] of Object.entries({
  async malformed_signature_is_an_auth_refusal() {
    const db = new FakeD1();
    db.db.prepare("INSERT INTO owners (id,email,tokenKey) VALUES (?,?,?)")
      .run(ref, "wire-auth@anticipy-test.invalid", "test-key");
    const env = { DB: asD1(db), ANTICIPY_AUTH_SECRET: "test-secret" };
    const token = await issueToken(env, ref, "test-key");
    assert.ok(await verifyToken(env, token), "positive auth control must work");
    for (const signature of ["!!!!", "a", "💣"]) {
      assert.equal(await verifyToken(env, token.split(".").slice(0, 2).join(".") + "." + signature), null);
    }
  },
  async generic_owner_delete_cannot_orphan_product_state() {
    for (const principal of [{ kind: "account", ownerId: ref }, { kind: "service" }, { kind: "superuser" }]) {
      const db = new FakeD1();
      db.db.prepare("INSERT INTO owners (id,email) VALUES (?,?)").run(ref, "delete@anticipy-test.invalid");
      db.db.prepare("INSERT INTO owner_profile (id,owner_ref,owner_id,name) VALUES (?,?,?,?)")
        .run("auditprofile001", ref, ref, "Synthetic person");
      const req = { collection: COLLECTIONS.owners, recordId: ref, principal, method: "DELETE" } as RecordsRequest;
      const response = await remove({ DB: asD1(db) }, req);
      assert.equal(response.status, 405);
      assert.equal(db.rows("SELECT * FROM owners WHERE id = ?", ref).length, 1);
      assert.equal(db.rows("SELECT * FROM owner_profile WHERE owner_ref = ?", ref).length, 1);
    }
  },
})) {
  try { await test(); console.log("PASS " + name); }
  catch (error) { failed++; console.error("FAIL " + name + ": " + (error as Error).message); }
}
if (failed) process.exit(1);
