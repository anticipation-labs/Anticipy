/** Account ownership is not permission to forge server delivery evidence.
 * Real Worker router/auth/policies/records SQL over an in-memory D1 twin only.
 */
import assert from "node:assert/strict";
import worker from "../src/index.ts";
import { issueToken } from "../src/api/auth.ts";
import { guard } from "../src/policy/guard.ts";
import type { Ctx } from "../src/policy/chain.ts";
import { FakeD1, asD1 } from "./fake-d1.ts";

const OWNER = "evidenceowner01";
const OTHER = "evidenceowner02";
const SERVICE = "server-evidence-test-service";
const BASE = "https://local-evidence-test.invalid";
const EVENTS = "/api/collections/events/records";
const PROTECTED = ["reply_outbox", "notification_status", "anticipy_text", "sms_reply"];
const originalFetch = globalThis.fetch;
globalThis.fetch = async () => { throw new Error("This suite permits no network"); };

async function rig() {
  const db = new FakeD1();
  for (const owner of [OWNER, OTHER]) {
    db.db.prepare("INSERT INTO owners (id,email,tokenKey) VALUES (?,?,?)")
      .run(owner, `${owner}@example.invalid`, `${owner}-key`);
  }
  const env = { DB: asD1(db), ANTICIPY_AUTH_SECRET: "server-evidence-test-auth",
    ANTICIPY_SERVICE_TOKEN: SERVICE };
  const token = await issueToken(env, OWNER, `${OWNER}-key`);
  const seed = (kind: string, owner = OWNER) => {
    const id = crypto.randomUUID().replaceAll("-", "").slice(0, 15);
    db.db.prepare("INSERT INTO events (id,owner_ref,device_id,kind,text,goal,decision) VALUES (?,?,?,?,?,?,?)")
      .run(id, owner, "server-evidence-fixture", kind, "original evidence", "original-target", "reply_pending");
    return id;
  };
  const request = async (method: string, path: string, body?: Record<string, unknown>,
                         identity: "account" | "service" | "anonymous" = "account", multipart = false) => {
    const headers: Record<string, string> = identity === "account" ? { Authorization: `Bearer ${token}` }
      : identity === "service" ? { "X-Anticipy-Token": SERVICE, "X-Anticipy-Worker": "1" } : {};
    let payload: BodyInit | undefined;
    if (body !== undefined) {
      if (multipart) {
        const form = new FormData();
        for (const [key, value] of Object.entries(body)) form.set(key, String(value));
        payload = form;
      } else {
        headers["Content-Type"] = "application/json";
        payload = JSON.stringify(body);
      }
    }
    return worker.fetch(new Request(BASE + path, { method, headers, body: payload }), env as never,
      { waitUntil() {}, passThroughOnException() {} } as never);
  };
  return { db, env, seed, request };
}

let failed = 0;
let passed = 0;
async function check(name: string, test: () => Promise<void>) {
  try { await test(); passed++; }
  catch (error) { failed++; console.error(`FAIL ${name}: ${(error as Error).message}`); }
}

for (const kind of PROTECTED) {
  for (const multipart of [false, true]) {
    await check(`account cannot create ${kind} via ${multipart ? "form" : "JSON"}`, async () => {
      const r = await rig();
      const response = await r.request("POST", EVENTS,
        { owner_ref: OWNER, device_id: "test", kind, text: "forged evidence" }, "account", multipart);
      assert.equal(response.status, 403);
      assert.equal(r.db.rows("SELECT id FROM events").length, 0);
    });
  }
  for (const [method, body] of [
    ["PATCH", { text: "rewritten", goal: "different-target", decision: "sms_delivered" }],
    ["PATCH", { kind: "app_reply", text: "laundered" }],
    ["PATCH", { kind: null }],
    ["DELETE", undefined],
  ] as const) {
    await check(`account cannot ${method} existing ${kind} (${String(body?.kind ?? "fields")})`, async () => {
      const r = await rig();
      const id = r.seed(kind);
      const before = r.db.rows("SELECT * FROM events WHERE id = ?", id);
      assert.equal((await r.request(method, `${EVENTS}/${id}`, body)).status, 403);
      assert.deepEqual(r.db.rows("SELECT * FROM events WHERE id = ?", id), before);
    });
  }
  await check(`account cannot turn a transcript into ${kind}`, async () => {
    const r = await rig();
    const id = r.seed("transcript");
    assert.equal((await r.request("PATCH", `${EVENTS}/${id}`, { kind })).status, 403);
    assert.equal(r.db.rows("SELECT kind FROM events WHERE id = ?", id)[0].kind, "transcript");
  });
  await check(`owner reads ${kind}; stranger remains isolated; service retains writes`, async () => {
    const r = await rig();
    const response = await r.request("POST", EVENTS,
      { owner_ref: OWNER, device_id: "service-test", kind, text: "server evidence" }, "service");
    assert.equal(response.status, 200);
    const row = await response.json() as { id: string };
    assert.equal((await r.request("GET", `${EVENTS}/${row.id}`)).status, 200);
    const filter = encodeURIComponent(`owner_ref="${OWNER}" && kind="${kind}"`);
    const listed = await r.request("GET", `${EVENTS}?filter=${filter}`);
    assert.equal(listed.status, 200);
    assert.equal((await listed.json() as { items: unknown[] }).items.length, 1);
    assert.equal((await r.request("GET", `${EVENTS}/${r.seed(kind, OTHER)}`)).status, 403);
    assert.equal((await r.request("PATCH", `${EVENTS}/${row.id}`, { decision: "sms_delivered" }, "service")).status, 200);
    assert.equal((await r.request("DELETE", `${EVENTS}/${row.id}`, undefined, "service")).status, 204);
  });
}

for (const kind of ["transcript", "app_reply", "profile"]) {
  await check(`legitimate account ${kind} lifecycle remains available`, async () => {
    const r = await rig();
    const created = await r.request("POST", EVENTS,
      { owner_ref: OWNER, device_id: "iphone-fixture", kind, text: "legitimate account input" });
    assert.equal(created.status, 200);
    const row = await created.json() as { id: string };
    assert.equal((await r.request("PATCH", `${EVENTS}/${row.id}`, { text: "corrected input" })).status, 200);
    assert.equal((await r.request("DELETE", `${EVENTS}/${row.id}`)).status, 204);
    const other = r.seed(kind, OTHER);
    assert.equal((await r.request("PATCH", `${EVENTS}/${other}`, { text: "wrong owner" })).status, 403);
    assert.equal((await r.request("DELETE", `${EVENTS}/${other}`)).status, 403);
  });
}

for (const kind of PROTECTED) {
  for (const method of ["PATCH", "DELETE"]) {
    await check(`a concurrent server transition to ${kind} survives account ${method}`, async () => {
      const r = await rig();
      const id = r.seed("transcript");
      let transitioned = false;
      r.db.failOn = sql => {
        if (!transitioned && (sql.startsWith('UPDATE "events"') || sql.startsWith('DELETE FROM "events"'))) {
          transitioned = true;
          // Model another request committing after the policy read but before
          // this request's actual SQL write. No fake handler/authorization.
          r.db.db.prepare("UPDATE events SET kind=?, text=? WHERE id=?")
            .run(kind, "concurrent server evidence", id);
        }
        return false;
      };
      const response = await r.request(method, `${EVENTS}/${id}`,
        method === "PATCH" ? { text: "late account overwrite", kind: "app_reply" } : undefined);
      assert.equal(transitioned, true, "race reached the actual write boundary");
      assert.equal(response.status, 404);
      const rows = r.db.rows("SELECT kind,text FROM events WHERE id=?", id);
      assert.equal(rows.length, 1);
      assert.equal(rows[0].kind, kind);
      assert.equal(rows[0].text, "concurrent server evidence");
    });
  }
}

await check("failed event lookup cannot authorize a write", async () => {
  const r = await rig();
  const id = r.seed("reply_outbox");
  r.db.failOn = sql => /SELECT.*FROM "events"/s.test(sql);
  const response = await r.request("PATCH", `${EVENTS}/${id}`, { decision: "reply_pending" });
  assert.equal(response.status, 403);
  assert.equal(r.db.rows("SELECT decision FROM events WHERE id = ?", id)[0].decision, "reply_pending");
});

await check("a forbidden row cannot disclose whether it is server evidence", async () => {
  const r = await rig();
  const ids = [r.seed("transcript", OTHER), ...PROTECTED.map(kind => r.seed(kind, OTHER)), "missingevent001"];
  for (const method of ["PATCH", "DELETE"]) {
    const replies = [];
    for (const id of ids) {
      const response = await r.request(method, `${EVENTS}/${id}`, method === "PATCH" ? { text: "not mine" } : undefined);
      assert.equal(response.status, 403);
      replies.push(await response.json());
    }
    for (const reply of replies) assert.deepEqual(reply, replies[0]);
  }
});

await check("superuser rung remains above the account-only restriction", async () => {
  const r = await rig();
  for (const method of ["POST", "PATCH", "DELETE"]) {
    const url = new URL(BASE + EVENTS + (method === "POST" ? "" : "/serverevent0001"));
    const ctx = { request: new Request(url, { method }), url, path: url.pathname, method,
      body: { owner_ref: OWNER, kind: "reply_outbox" }, principal: { kind: "superuser", id: "test-admin" },
      worker: { fromWorker: false }, forcedScope: null, extraAst: null, db: r.env.DB } as Ctx;
    assert.equal(await guard(ctx, r.env), null);
  }
});

globalThis.fetch = originalFetch;
console.log(`server-authored event evidence: ${passed} passed, ${failed} failed`);
if (failed) process.exit(1);
