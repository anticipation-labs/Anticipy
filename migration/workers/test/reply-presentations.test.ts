/** Real read-only handler + SQL + schema; no provider or production traffic. */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import worker from "../src/index.ts";
import { replyPresentations } from "../src/routes/reply_presentations.ts";
import { FakeD1, asD1 } from "./fake-d1.ts";

const OWNER = "owner0000000001", OTHER = "owner0000000002";
const INBOUND = "inbound00000001", JOB = "task00000000001";
const SENDER = "+15550000001", TOKEN = "reply-presentations-test-service";
const BEFORE = "2026-09-08 10:00:00.000Z", INSTANT = "2026-09-08 11:00:00.000Z";
const DIGEST = createHash("sha256").update(SENDER).digest("hex");
const originalFetch = globalThis.fetch;
globalThis.fetch = async () => { throw new Error("This suite permits no network"); };

function rig() {
  const db = new FakeD1();
  const env = { DB: asD1(db), ANTICIPY_SERVICE_TOKEN: TOKEN };
  let sequence = 0;
  const event = (kind: string, fields: Record<string, unknown> = {}) => {
    const row = { id: `event${String(++sequence).padStart(10, "0")}`, kind, device_id: "test-fixture",
      owner_ref: OWNER, created: BEFORE, updated: BEFORE, text: "", goal: "", decision: "",
      external_event_id: "", ...fields };
    const keys = Object.keys(row);
    db.db.prepare(`INSERT INTO events (${keys.map(key => '"' + key + '"').join(",")}) VALUES (${keys.map(() => "?").join(",")})`)
      .run(...Object.values(row) as string[]);
    return row.id;
  };
  event("sms_reply", { id: INBOUND, goal: SENDER, created: INSTANT, updated: INSTANT });
  db.db.prepare("INSERT INTO jobs (id,owner_ref,goal,status) VALUES (?,?,?,?)")
    .run(JOB, OWNER, "fixture task", "awaiting_confirm");
  const chain = (options: { owner?: string; purpose?: string; job?: string; version?: number; at?: string } = {}) => {
    const owner = options.owner || OWNER;
    const time = options.at || BEFORE;
    const message = event("anticipy_text", { owner_ref: owner, text: "A concrete presented question", created: time, updated: time });
    const snapshot = { purpose: options.purpose || "task_question", job_id: options.job || JOB,
      version: options.version || 1, owner_ref: owner, binding_version: 1 };
    const outbox = event("reply_outbox", { owner_ref: owner, text: JSON.stringify(snapshot), goal: message,
      external_event_id: `reply-outbox:${message}`, created: time, updated: time });
    const attempt = event("notification_status", { owner_ref: owner, goal: message,
      external_event_id: `reply-sms:${message}`, decision: "sms_delivered", created: time, updated: time,
      text: JSON.stringify({ provider_id: "synthetic-provider-handle", recipient_digest: DIGEST }) });
    return { message, outbox, attempt, snapshot };
  };
  const request = async (body: unknown = { owner_ref: OWNER, event_id: INBOUND }, token: string | null = TOKEN, method = "POST") => {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (token !== null) headers["X-Anticipy-Token"] = token;
    return replyPresentations(new Request("https://local-presentations.invalid/worker/reply-presentations", {
      method, headers, body: method === "GET" ? undefined : JSON.stringify(body),
    }), env);
  };
  const change = (id: string, field: string, value: string) => db.db.prepare(`UPDATE events SET "${field}"=? WHERE id=?`).run(value, id);
  return { db, env, chain, event, request, change };
}

let passed = 0, failed = 0;
async function check(name: string, test: () => Promise<void>) {
  try { await test(); passed++; }
  catch (error) { failed++; console.error(`FAIL ${name}: ${(error as Error).message}`); }
}

await check("a genuine delivered chain is returned without sender/provider handle", async () => {
  const r = rig(), c = r.chain();
  const response = await r.request();
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("cache-control"), "no-store");
  const body = await response.json() as any;
  assert.equal(body.complete, true);
  assert.equal(body.recipient_digest, DIGEST);
  assert.equal(body.inbound_created, INSTANT);
  assert.deepEqual(body.presentations.map((row: any) => row.presentation_id), [c.outbox]);
  assert.deepEqual(body.presentations[0].snapshot, c.snapshot);
  assert.deepEqual(body.messages.map((row: any) => row.id), [c.message]);
  assert(!JSON.stringify(body).includes(SENDER));
  assert(!JSON.stringify(body).includes("synthetic-provider-handle"));
  assert(r.db.log.every(sql => /^\s*SELECT\b/i.test(sql)), "no DB mutation");
});

await check("the production Worker dispatches the service-only route", async () => {
  const r = rig(), c = r.chain();
  for (const authenticated of [false, true]) {
    r.db.log.length = 0;
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (authenticated) headers["X-Anticipy-Token"] = TOKEN;
    const response = await worker.fetch(new Request("https://local-presentations.invalid/worker/reply-presentations", {
      method: "POST", headers, body: JSON.stringify({ owner_ref: OWNER, event_id: INBOUND }),
    }), r.env as never, { waitUntil() {}, passThroughOnException() {} } as never);
    assert.equal(response.status, authenticated ? 200 : 401);
    if (authenticated) {
      const body = await response.json() as any;
      assert.equal(body.presentations[0].presentation_id, c.outbox);
    } else { assert.deepEqual(r.db.log, []); }
  }
});

await check("every revision of current open work survives over 1000 unrelated messages", async () => {
  const r = rig();
  const a = r.chain({ version: 1 }), b = r.chain({ version: 2, at: "2026-09-08 10:01:00.000Z" });
  for (let i = 0; i < 1005; i++) r.chain({ purpose: "ordinary_reply" });
  const response = await r.request();
  const body = await response.json() as any;
  assert.equal(response.status, 200);
  assert.equal(body.complete, true);
  assert.deepEqual(body.presentations.map((row: any) => row.presentation_id), [b.outbox, a.outbox]);
  assert.equal(body.messages.length, 40);
});

await check("201 active task presentations explicitly deny completeness", async () => {
  const r = rig();
  for (let i = 0; i < 201; i++) r.chain({ version: i + 1 });
  const body = await (await r.request()).json() as any;
  assert.equal(body.complete, false);
  assert.deepEqual(body.presentations, []);
  assert.equal(body.messages.length, 40);
});

for (const state of ["awaiting_confirm", "needs_user", "queued", "running", "done", "failed", "cancelled"]) {
  await check(`current job state ${state} controls candidacy, not thread context`, async () => {
    const r = rig(); r.chain();
    r.db.db.prepare("UPDATE jobs SET status=? WHERE id=?").run(state, JOB);
    const body = await (await r.request()).json() as any;
    assert.equal(body.presentations.length, ["awaiting_confirm", "needs_user", "queued"].includes(state) ? 1 : 0);
    assert.equal(body.messages.length, 1);
  });
}

for (const token of [null, "", "incorrect-token"]) {
  await check("unauthenticated requests touch no database", async () => {
    const r = rig();
    assert.equal((await r.request(undefined, token)).status, 401);
    assert.deepEqual(r.db.log, []);
  });
}
await check("unconfigured token and wrong method refuse without reading", async () => {
  const r = rig(); r.env.ANTICIPY_SERVICE_TOKEN = "";
  assert.equal((await r.request()).status, 401);
  assert.equal((await r.request(undefined, TOKEN, "GET")).status, 405);
  assert.deepEqual(r.db.log, []);
});
for (const body of [null, [], "not an object", {}, { owner_ref: OWNER }, { owner_ref: OWNER, event_id: "wrong" },
  { owner_ref: OTHER + " ", event_id: INBOUND }, { owner_ref: OWNER, event_id: INBOUND, sender: SENDER }]) {
  await check("malformed or extra identity fields refuse before reading", async () => {
    const r = rig();
    assert.equal((await r.request(body)).status, 400);
    assert.deepEqual(r.db.log, []);
  });
}

await check("wrong owner and missing input do not disclose inbound identity", async () => {
  const r = rig();
  const other = await r.request({ owner_ref: OTHER, event_id: INBOUND });
  const missing = await r.request({ owner_ref: OWNER, event_id: "missing00000001" });
  assert.equal(other.status, 404); assert.equal(missing.status, 404);
  assert.deepEqual(await other.json(), await missing.json());
});

for (const [field, value] of [["kind", "transcript"], ["goal", ""], ["created", ""], ["created", "tomorrow"], ["created", "123"]]) {
  await check(`inbound requires valid ${field}`, async () => {
    const r = rig(); r.chain(); r.change(INBOUND, field, value);
    assert.equal((await r.request()).status, 400);
  });
}

for (const leg of ["message", "outbox", "attempt"] as const) {
  for (const field of ["created", "updated"]) {
    for (const value of [INSTANT, "2026-09-08 12:00:00.000Z", "not-a-time"]) {
      await check(`${leg}.${field} ${value} cannot testify before inbound`, async () => {
        const r = rig(), c = r.chain(); r.change(c[leg], field, value);
        const body = await (await r.request()).json() as any;
        assert.equal(body.complete, true); assert.deepEqual(body.presentations, []); assert.deepEqual(body.messages, []);
      });
    }
  }
  await check(`mixed-owner ${leg} chain is excluded`, async () => {
    const r = rig(), c = r.chain(); r.change(c[leg], "owner_ref", OTHER);
    const body = await (await r.request()).json() as any;
    assert.deepEqual(body.presentations, []); assert.deepEqual(body.messages, []);
  });
}

for (const metadata of ["malformed-json", "[]", "null", JSON.stringify({ provider_id: "", recipient_digest: DIGEST }),
  JSON.stringify({ provider_id: 123, recipient_digest: DIGEST }), JSON.stringify({ provider_id: "receipt", recipient_digest: "other" })]) {
  await check("missing or wrong receipt evidence cannot authorize a presentation", async () => {
    const r = rig(), c = r.chain(); r.change(c.attempt, "text", metadata);
    const response = await r.request(); assert.equal(response.status, 200);
    const body = await response.json() as any;
    assert.deepEqual(body.presentations, []); assert.deepEqual(body.messages, []);
  });
}
for (const decision of ["sms_accepted", "sms_unconfirmed", "sms_mock", "sms_skipped"]) {
  await check(`${decision} is not delivery`, async () => {
    const r = rig(), c = r.chain(); r.change(c.attempt, "decision", decision);
    const body = await (await r.request()).json() as any;
    assert.deepEqual(body.presentations, []); assert.deepEqual(body.messages, []);
  });
}
await check("unrelated foreign job cannot be used as active authority", async () => {
  const r = rig(); r.chain(); r.db.db.prepare("UPDATE jobs SET owner_ref=? WHERE id=?").run(OTHER, JOB);
  const body = await (await r.request()).json() as any;
  assert.deepEqual(body.presentations, []); assert.equal(body.messages.length, 1);
});
await check("malformed outbox metadata is only non-authoritative thread context", async () => {
  const r = rig(), c = r.chain(); r.change(c.outbox, "text", "malformed-json");
  const response = await r.request(); assert.equal(response.status, 200);
  const body = await response.json() as any;
  assert.deepEqual(body.presentations, []); assert.equal(body.messages.length, 1);
});
for (const leg of ["outbox", "attempt"] as const) {
  for (const field of ["goal", "external_event_id", "kind"]) {
    await check(`${leg} requires canonical ${field}`, async () => {
      const r = rig(), c = r.chain(); r.change(c[leg], field, "wrong-identity");
      const body = await (await r.request()).json() as any;
      assert.deepEqual(body.presentations, []); assert.deepEqual(body.messages, []);
    });
  }
}
await check("storage failures stay unknown without leaking details", async () => {
  const r = rig(); r.chain(); r.db.failOn = () => true;
  const response = await r.request(); assert.equal(response.status, 503);
  const body = await response.text();
  assert(!body.includes("SELECT")); assert(!body.includes(OWNER)); assert(!body.includes(SENDER));
});

for (const corruptCandidates of [true, false]) {
  for (const malformed of [{ success: true }, { success: true, results: null },
    { success: true, results: {} }, { success: false, results: [] }, { results: [] }]) {
    await check("unknown D1 result cannot become verified empty evidence", async () => {
      const r = rig(); r.chain();
      r.env.DB = { prepare(sql: string) {
        const candidateQuery = sql.includes("AS presentation_id");
        const recentQuery = sql.includes("FROM events m") && !candidateQuery;
        if (corruptCandidates ? candidateQuery : recentQuery) {
          return { bind() { return { all: async () => malformed }; } };
        }
        return r.db.prepare(sql);
      } } as unknown as D1Database;
      assert.equal((await r.request()).status, 503);
    });
  }
}

globalThis.fetch = originalFetch;
console.log(`reply presentations: ${passed} passed, ${failed} failed`);
if (failed) process.exit(1);
