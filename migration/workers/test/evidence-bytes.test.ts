/**
 * Runs with no network and no D1 (an in-process SQLite one carrying the real
 * migration/d1/schema.sql):
 *
 *   node --experimental-strip-types migration/workers/test/evidence-bytes.test.ts
 *
 * "DONE = EVIDENCE", END TO END, THROUGH THE REAL ROUTER (audit F13).
 *
 * Three links were missing and each one alone was enough to break the promise
 * in evidence.pb.js:9-17:
 *
 *   1. index.ts's readBody returned null for anything that was not JSON, so
 *      the extension's multipart deposit (background.js:1364-1377) reached the
 *      guard as an EMPTY BODY: owner_ref read "", the agent rung refused it,
 *      403, "could not deposit the receipt photo".
 *   2. Nothing in src/ ever called EVIDENCE.put. The bucket was bound and
 *      written to by nothing; the only R2 verb in the tree was a .get.
 *   3. POST /evidence/share was not routed and GET /api/files/* was not
 *      routed, so assets.ts:serveFile — written, commented and correct — was
 *      dead code, and brain/evidence.py logged "the share door answered 404"
 *      on every send.
 *
 * So the checks below go through `worker.fetch`, not through the pieces: a
 * function that works while its route does not is exactly what shipped.
 *
 * MUTATIONS THIS FILE MUST GO RED ON: multipart parsing removed from readBody;
 * the R2 put removed; either route unwired; the share window's fetch ceiling
 * or its expiry not enforced; a deposit with no picture accepted.
 */
import assert from "node:assert/strict";
import worker from "../src/index.ts";
import { evidenceFilename, EVIDENCE_MAX_BYTES } from "../src/assets.ts";
import { openTestD1, fakeR2, type TestDb, type FakeR2 } from "./sqlite-d1.ts";

let failures = 0;
let passes = 0;
async function check(what: string, fn: () => void | Promise<void>): Promise<void> {
  try { await fn(); passes++; }
  catch (err) { failures++; console.error("FAIL " + what + "\n     " + (err as Error).message); }
}
const realLog = console.log;
console.log = () => { /* the routes narrate */ };

const SERVICE = "service-token-0123456789abcdef";
const OWNER = "owner000000one1";
const OTHER = "owner000000two2";
const AGENT_TOKEN = "agenttoken".repeat(5);          // >= 40 chars, as the column demands
const JOB = "job000000000001";
const HOST = "https://api.anticipy.ai";

function rig() {
  const t = openTestD1();
  const r2 = fakeR2();
  const now = "2026-09-05 12:00:00.000Z";
  for (const id of [OWNER, OTHER]) {
    t.exec(`INSERT INTO owners (id, created, updated, email, emailVisibility, verified, password, tokenKey, phone, legacy_uuid)
            VALUES ('${id}', '${now}', '${now}', '${id}@example.invalid', 0, 0, '', 'tk-${id}', '', '')`);
  }
  t.exec(`INSERT INTO jobs (id, created, updated, goal, status, owner_ref, device_id)
          VALUES ('${JOB}', '${now}', '${now}', 'book the table', 'running', '${OWNER}', 'chrome')`);
  t.exec(`INSERT INTO agents (id, created, updated, agent_id, agent_token, pair_code, paired, owner_ref)
          VALUES ('agent000000001', '${now}', '${now}', 'agent-1', '${AGENT_TOKEN}', 'PAIR01', 1, '${OWNER}')`);
  const env = {
    DB: t.db, EVIDENCE: r2.bucket,
    ASSETS: { fetch: async () => new Response("static", { status: 200 }) },
    ANTICIPY_SERVICE_TOKEN: SERVICE,
    ANTICIPY_PUBLIC_URL: "https://api.anticipy.ai",
  };
  return { t, r2, env };
}

const ctx = { waitUntil() {}, passThroughOnException() {} } as unknown as ExecutionContext;
const fetchIt = (env: unknown, req: Request) =>
  worker.fetch(req, env as never, ctx);

/** The extension's own shape: FormData, no Content-Type of its own. */
function deposit(fields: Record<string, string>, bytes?: Uint8Array, type = "image/jpeg", name = "receipt.jpg") {
  const form = new FormData();
  for (const [k, v] of Object.entries(fields)) form.append(k, v);
  if (bytes) form.append("image", new Blob([bytes as BlobPart], { type }), name);
  return new Request(`${HOST}/api/collections/evidence/records`, {
    method: "POST", body: form,
    headers: { "X-Anticipy-Agent-ID": "agent-1", "X-Anticipy-Agent-Token": AGENT_TOKEN },
  });
}

const JPEG = new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 1, 2, 3, 4]);

// ---------------------------------------------------------------------------
// 1. The deposit
// ---------------------------------------------------------------------------

await check("the extension's multipart deposit is accepted, and its bytes land in R2", async () => {
  const { t, r2, env } = rig();
  const res = await fetchIt(env, deposit({ owner_ref: OWNER, job: JOB, effect_key: "ek-1" }, JPEG));
  const row = await res.json() as { id: string; image: string; owner_ref: string; job: string };
  assert.equal(res.status, 200, JSON.stringify(row));
  assert.equal(row.owner_ref, OWNER, "the form's string fields never reached the row");
  assert.equal(row.job, JOB);
  assert.ok(row.image, "the row names no picture");
  const stored = r2.objects.get(`evidence/${row.id}/${row.image}`);
  assert.ok(stored, "no bytes were written to R2: " + [...r2.objects.keys()].join(","));
  assert.deepEqual([...stored!.bytes], [...JPEG]);
  assert.equal(stored!.contentType, "image/jpeg");
  t.close();
});

await check("the guard sees owner_ref, which is what a 403 used to hide", async () => {
  // guard.pb.js:342-346 admits a deposit for the credential's OWN owner and
  // nothing else. With the body dropped the comparison was ""!==owner and
  // every deposit was refused — the defect looked like an authorisation
  // problem and was a parsing one.
  const { t, env } = rig();
  const mine = await fetchIt(env, deposit({ owner_ref: OWNER, job: JOB }, JPEG));
  assert.equal(mine.status, 200);
  const theirs = await fetchIt(env, deposit({ owner_ref: OTHER, job: JOB }, JPEG));
  assert.equal(theirs.status, 403, "an agent deposited for another owner");
  t.close();
});

await check("a deposit with NO picture is refused, not stored as an empty row", async () => {
  // Measured on live D1: row 48mu1cxcrpwjfp2, owner_ref "", job "", image "" —
  // unservable, unfindable and undeletable by the person it belongs to.
  const { t, r2, env } = rig();
  const res = await fetchIt(env, deposit({ owner_ref: OWNER, job: JOB }));
  assert.equal(res.status, 400);
  const body = await res.json() as { data: Record<string, { code: string }> };
  assert.equal(body.data.image.code, "validation_required");
  assert.equal(t.query("SELECT id FROM evidence").length, 0, "an empty evidence row was written");
  assert.equal(r2.objects.size, 0);
  t.close();
});

await check("an evidence host is not a file host: the MIME list and the size ceiling hold", async () => {
  const { t, r2, env } = rig();
  const pdf = await fetchIt(env, deposit({ owner_ref: OWNER, job: JOB },
    new Uint8Array([37, 80, 68, 70]), "application/pdf", "invoice.pdf"));
  assert.equal(pdf.status, 400, "a PDF was accepted by the evidence host");

  const huge = await fetchIt(env, deposit({ owner_ref: OWNER, job: JOB },
    new Uint8Array(EVIDENCE_MAX_BYTES + 1)));
  assert.equal(huge.status, 400, "a file over the field's ceiling was accepted");

  assert.equal(t.query("SELECT id FROM evidence").length, 0);
  assert.equal(r2.objects.size, 0, "refused uploads still left bytes behind");
  t.close();
});

await check("a refused row takes its bytes back out of the bucket", async () => {
  // `job` is CHECK(length > 0) in D1, so this create fails after the put.
  const { t, r2, env } = rig();
  // D1 answers a CHECK violation by THROWING, and records.create rethrows
  // anything that is not a known column or a unique collision — so the failure
  // arrives as an exception, not a status, and the cleanup has to be on both
  // paths. That is what the platform would turn into a 1101.
  await assert.rejects(() => fetchIt(env, deposit({ owner_ref: OWNER, job: "" }, JPEG)));
  assert.equal(t.query("SELECT id FROM evidence").length, 0);
  assert.equal(r2.objects.size, 0, "an orphaned object was left in R2, paid for forever");
  t.close();
});

await check("the stored filename is not the one the browser sent", async () => {
  // PocketBase appended 10 random characters to every stored name, and the
  // share URL is built from it. evidence.pb.js:24-26 is explicit that this is
  // a delay and not a lock — which is why the window and the ceiling exist.
  const a = evidenceFilename("receipt.jpg", "image/jpeg");
  const b = evidenceFilename("receipt.jpg", "image/jpeg");
  assert.notEqual(a, b);
  assert.match(a, /^receipt_[a-z0-9]{10}\.jpg$/);
  assert.match(evidenceFilename("../../etc/passwd", "image/png"), /^[a-z0-9_]+_[a-z0-9]{10}\.png$/);
  assert.equal(evidenceFilename("", "image/png").startsWith("receipt_"), true);
});

// ---------------------------------------------------------------------------
// 2. The two doors that are not the public one
// ---------------------------------------------------------------------------

async function deposited(env: unknown): Promise<{ id: string; image: string }> {
  const res = await fetchIt(env, deposit({ owner_ref: OWNER, job: JOB }, JPEG));
  return await res.json() as { id: string; image: string };
}

await check("GET /api/files/* is routed at all — it was dead code behind a generic 404", async () => {
  const { t, env } = rig();
  const row = await deposited(env);
  const res = await fetchIt(env, new Request(`${HOST}/api/files/evidence/${row.id}/${row.image}`, {
    headers: { "X-Anticipy-Token": SERVICE },
  }));
  assert.equal(res.status, 200, "the evidence door is still not wired");
  assert.equal(res.headers.get("content-type"), "image/jpeg");
  assert.equal(res.headers.get("cache-control"), "private, no-store");
  assert.deepEqual([...new Uint8Array(await res.arrayBuffer())], [...JPEG]);
  t.close();
});

await check("a picture with no share window is not on the internet", async () => {
  // THE PROPERTY EVERYTHING ELSE RESTS ON (evidence.pb.js:20-23): the normal
  // state of an evidence photo is "not on the internet".
  const { t, env } = rig();
  const row = await deposited(env);
  const res = await fetchIt(env, new Request(`${HOST}/api/files/evidence/${row.id}/${row.image}`));
  assert.equal(res.status, 404);
  assert.equal((await res.json() as { error: string }).error, "that evidence is not available");
  t.close();
});

await check("every other collection fails closed at the same door", async () => {
  const { t, env } = rig();
  const row = await deposited(env);
  const res = await fetchIt(env, new Request(
    `${HOST}/api/files/owner_profile/${row.id}/${row.image}`,
    { headers: { "X-Anticipy-Token": SERVICE } }));
  assert.equal(res.status, 404);
  assert.equal((await res.json() as { error: string }).error, "that evidence is not available");
  t.close();
});

// ---------------------------------------------------------------------------
// 3. The share mint and the public door
// ---------------------------------------------------------------------------

const share = (env: unknown, body: unknown, token = SERVICE) =>
  fetchIt(env, new Request(`${HOST}/evidence/share`, {
    method: "POST", body: JSON.stringify(body),
    headers: { "content-type": "application/json", "X-Anticipy-Token": token },
  }));

await check("the share mint needs the service token", async () => {
  const { t, env } = rig();
  const res = await fetchIt(env, new Request(`${HOST}/evidence/share`, {
    method: "POST", body: JSON.stringify({ id: "x" }),
    headers: { "content-type": "application/json" },
  }));
  assert.equal(res.status, 403);
  assert.equal((await res.json() as { error: string }).error, "forbidden");
  t.close();
});

await check("an absent picture is an answer, not an error — a 404 MediaUrl fails the WHOLE text", async () => {
  const { t, env } = rig();
  for (const [body, reason] of [
    [{}, "no evidence was named"],
    [{ id: "nosuchrecord01" }, "that evidence is gone"],
  ] as [unknown, string][]) {
    const res = await share(env, body);
    assert.equal(res.status, 200, "the share door answered a status brain/evidence.py reads as failure");
    const got = await res.json() as { ok: boolean; reason: string; url: string };
    assert.equal(got.ok, false);
    assert.equal(got.reason, reason);
    assert.equal(got.url, "");
  }
  t.close();
});

await check("a minted window is fifteen minutes and five fetches, then the picture is gone", async () => {
  const { t, env } = rig();
  const row = await deposited(env);
  const minted = await share(env, { id: row.id });
  const got = await minted.json() as { ok: boolean; url: string; expires: string; fetches: number };
  assert.equal(got.ok, true, JSON.stringify(got));
  assert.equal(got.url, `${HOST}/api/files/evidence/${row.id}/${row.image}`);
  assert.equal(got.fetches, 5);
  const window = Date.parse(got.expires) - Date.now();
  assert.ok(window > 14 * 60_000 && window <= 15 * 60_000, `window was ${window}ms`);

  // Anonymous, the way Twilio fetches: five come through, the sixth does not.
  for (let i = 1; i <= 5; i++) {
    const res = await fetchIt(env, new Request(got.url));
    assert.equal(res.status, 200, `fetch ${i} of 5 was refused`);
  }
  const sixth = await fetchIt(env, new Request(got.url));
  assert.equal(sixth.status, 404, "the fetch ceiling did not close the window");
  assert.equal((await sixth.json() as { error: string }).error, "that evidence is not available");
  t.close();
});

await check("re-sharing gives a fresh ceiling, or the second text silently loses its photo", async () => {
  const { t, env } = rig();
  const row = await deposited(env);
  const first = await (await share(env, { id: row.id })).json() as { url: string };
  for (let i = 0; i < 5; i++) await fetchIt(env, new Request(first.url));
  assert.equal((await fetchIt(env, new Request(first.url))).status, 404);

  await share(env, { id: row.id });
  assert.equal((await fetchIt(env, new Request(first.url))).status, 200,
    "a re-shared picture opened a window nothing could come through");
  t.close();
});

await check("an EXPIRED window is closed, and an unparseable one is not the far future", async () => {
  // `new Date("soon").getTime()` is NaN and `NaN <= now` is FALSE, so the
  // obvious expiry test lets an unreadable date through as the far future.
  const { t, env } = rig();
  const row = await deposited(env);
  const url = `${HOST}/api/files/evidence/${row.id}/${row.image}`;
  for (const value of ["2020-01-01T00:00:00.000Z", "soon", ""]) {
    t.exec(`UPDATE evidence SET share_expires = '${value}', fetches = 0 WHERE id = '${row.id}'`);
    const res = await fetchIt(env, new Request(url));
    assert.equal(res.status, 404, `share_expires ${JSON.stringify(value)} served the picture`);
  }
  t.close();
});

await check("a fetch that cannot be counted is refused — serving what nobody counts is the hole", async () => {
  const { t, env } = rig();
  const row = await deposited(env);
  const got = await (await share(env, { id: row.id })).json() as { url: string };
  const broken = { ...env, DB: {
    prepare: (sql: string) => {
      const stmt = t.db.prepare(sql);
      if (!sql.startsWith("UPDATE")) return stmt;
      return { bind: () => ({ run: async () => { throw new Error("D1 is unreachable"); } }) };
    },
  } };
  const res = await fetchIt(broken, new Request(got.url));
  assert.equal(res.status, 404, "the picture was served without spending a fetch");
  t.close();
});

await check("the owner's own picture needs no window and spends no fetch", async () => {
  // "the picture in his own app is not the picture on the public internet, and
  // must not need one to exist."
  const { t, env } = rig();
  const row = await deposited(env);
  for (let i = 0; i < 8; i++) {
    const res = await fetchIt(env, new Request(`${HOST}/api/files/evidence/${row.id}/${row.image}`, {
      headers: { "X-Anticipy-Token": SERVICE },
    }));
    assert.equal(res.status, 200, `the service door closed after ${i} fetches`);
  }
  const spent = t.query<{ fetches: number }>(
    "SELECT fetches FROM evidence WHERE id = ?", row.id)[0].fetches;
  assert.equal(spent, 0, "the owner's own read spent Twilio's ceiling");
  t.close();
});

await check("with no https base configured the answer is ok:false, never a URL that breaks at Twilio", async () => {
  const { t, r2, env } = rig();
  const bare = { ...env, ANTICIPY_PUBLIC_URL: "" };
  const row = await deposited(bare);
  const res = await fetchIt(bare, new Request("http://127.0.0.1:8787/evidence/share", {
    method: "POST", body: JSON.stringify({ id: row.id }),
    headers: { "content-type": "application/json", "X-Anticipy-Token": SERVICE },
  }));
  const got = await res.json() as { ok: boolean; reason: string };
  assert.equal(res.status, 200);
  assert.equal(got.ok, false);
  assert.equal(got.reason, "no https base url is configured for this backend");
  assert.equal(r2.objects.size, 1);
  t.close();
});

await check("a row with no picture cannot be shared", async () => {
  const { t, env } = rig();
  const now = "2026-09-05 12:00:00.000Z";
  t.exec(`INSERT INTO evidence (id, created, updated, owner_ref, job, effect_key, image, share_expires, fetches)
          VALUES ('evd000000000001', '${now}', '${now}', '${OWNER}', '${JOB}', '', '', '', 0)`);
  const got = await (await share(env, { id: "evd000000000001" })).json() as { ok: boolean; reason: string };
  assert.equal(got.ok, false);
  assert.equal(got.reason, "that evidence has no picture");
  t.close();
});

console.log = realLog;
console.log(`evidence-bytes: ${passes} checks passed, ${failures} failed`);
if (failures) process.exit(1);
