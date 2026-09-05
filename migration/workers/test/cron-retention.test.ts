/**
 * Runs with no network and no D1 (an in-process SQLite one carrying the real
 * migration/d1/schema.sql):
 *
 *   node --experimental-strip-types migration/workers/test/cron-retention.test.ts
 *
 * THE TWO RECORD-LEVEL SWEEPS THAT HAD NO HOME ON CLOUDFLARE (audit F27,
 * migration/CRITIQUE.md §1.4 items 2 and 3).
 *
 * audit_retention.pb.js:71-83 trimmed the model-audit ledger on every write;
 * evidence.pb.js:244-269 capped receipt photos at 20 an owner and 60 in total.
 * Both were `onRecordAfterCreateSuccess` hooks, and a Worker has none — so
 * llm.ts:311 went on saying "KEEP audit_retention's sweep" while nothing did.
 * Measured on live D1 2026-09-05: 102 audit rows, 12.4 MB of payload JSON,
 * about 72% of the whole database, still growing.
 *
 * The 5 GB volume this hook was written for filled once already, and the
 * symptom was a password-reset code that could be texted but never stored.
 *
 * These checks drive the real `scheduled` handler on the real cron string, so
 * a sweep that exists but is never dispatched fails here.
 *
 * MUTATIONS THIS FILE MUST GO RED ON: either sweep never called from prune;
 * the ledger cap raised so it never bites; the R2 objects left behind when
 * their rows go; the evidence delete ordered before the row delete (bytes gone
 * while the row still points at them).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { scheduled, type CronEnv } from "../src/cron.ts";
import { openTestD1, fakeR2, type TestDb, type FakeR2 } from "./sqlite-d1.ts";

// THE THREE NUMBERS ARE READ OUT OF THE HOOKS, not typed here. They are the
// ceilings the original authors chose against a volume that had already filled
// once, with the arithmetic written beside them (evidence.pb.js:226-243). A
// test that typed them would pass while the Worker and the oracle disagreed.
const here = dirname(fileURLToPath(import.meta.url));
const hooks = join(here, "..", "..", "..", "backend", "pb_hooks");
function constFromHook(file: string, name: string): number {
  const src = readFileSync(join(hooks, file), "utf8");
  const m = new RegExp("const " + name + " = (\\d+)").exec(src);
  assert.ok(m, `${file} no longer declares ${name}`);
  return Number(m![1]);
}
const AUDIT_KEEP = constFromHook("audit_retention.pb.js", "AUDIT_KEEP");
const EVIDENCE_PER_OWNER = constFromHook("evidence.pb.js", "KEEP_PER_OWNER");
const EVIDENCE_TOTAL = constFromHook("evidence.pb.js", "KEEP_TOTAL");

let failures = 0;
let passes = 0;
async function check(what: string, fn: () => void | Promise<void>): Promise<void> {
  try { await fn(); passes++; }
  catch (err) { failures++; console.error("FAIL " + what + "\n     " + (err as Error).message); }
}

const logs: string[] = [];
const realLog = console.log;
console.log = (...a: unknown[]) => { logs.push(a.map(String).join(" ")); };

/** `17 4 * * *` — the string wrangler.jsonc registers and the Worker dispatches on. */
const PRUNE_CRON = "17 4 * * *";

function env(t: TestDb, r2?: FakeR2): CronEnv {
  return {
    DB: t.db, EVIDENCE: r2?.bucket,
    TWILIO_ACCOUNT_SID: "", TWILIO_AUTH_TOKEN: "", TWILIO_PHONE_NUMBER: "",
  } as unknown as CronEnv;
}

/** The Worker's own dispatch, plus the waitUntil the runtime would have awaited. */
async function runCron(e: CronEnv, cron = PRUNE_CRON): Promise<void> {
  const waited: Promise<unknown>[] = [];
  const ctx = { waitUntil: (p: Promise<unknown>) => { waited.push(p); }, passThroughOnException() {} };
  await scheduled({ cron, scheduledTime: Date.now(), noRetry() {} } as unknown as ScheduledController,
                  e, ctx as unknown as ExecutionContext);
  await Promise.all(waited);
}

function seedAudit(t: TestDb, n: number): void {
  for (let i = 0; i < n; i++) {
    const stamp = `2026-09-${String(1 + (i % 28)).padStart(2, "0")} 00:00:${String(i % 60).padStart(2, "0")}.${String(i).padStart(3, "0")}Z`;
    // Every NOT-NULL-and-non-empty column the real table demands, including
    // the payload JSON that made this table 72% of the database.
    t.exec(`INSERT INTO agent_llm_audit
              (id, created, agent_id, task_tag, owner_ref, model, status,
               client_request_json, proxy_version)
            VALUES ('aud${String(i).padStart(12, "0")}', '${stamp}', 'agent1', 'tag',
                    'owner000000one1', 'google/gemini-3.1-pro-preview', 'ok',
                    '{"messages":[]}', 'worker-1')`);
  }
}

function seedEvidence(t: TestDb, r2: FakeR2, owner: string, n: number, from = 0): string[] {
  const ids: string[] = [];
  for (let i = from; i < from + n; i++) {
    const id = `${owner.slice(0, 6)}ev${String(i).padStart(7, "0")}`;
    const stamp = `2026-09-05 ${String(Math.floor(i / 60) % 24).padStart(2, "0")}:${String(i % 60).padStart(2, "0")}:00.000Z`;
    t.exec(`INSERT INTO evidence (id, created, updated, owner_ref, job, effect_key, image, share_expires, fetches)
            VALUES ('${id}', '${stamp}', '${stamp}', '${owner}', 'job1', '', 'receipt.jpg', '', 0)`);
    r2.objects.set(`evidence/${id}/receipt.jpg`, { bytes: new Uint8Array([1, 2, 3]), contentType: "image/jpeg" });
    ids.push(id);
  }
  return ids;
}

const auditCount = (t: TestDb) =>
  t.query<{ n: number }>("SELECT COUNT(*) AS n FROM agent_llm_audit")[0].n;
const evidenceCount = (t: TestDb) =>
  t.query<{ n: number }>("SELECT COUNT(*) AS n FROM evidence")[0].n;

// ---------------------------------------------------------------------------
// The audit ledger
// ---------------------------------------------------------------------------

await check("the daily prune caps the model-audit ledger at 300", async () => {
  const t = openTestD1();
  seedAudit(t, AUDIT_KEEP + 120);
  assert.equal(auditCount(t), AUDIT_KEEP + 120);
  await runCron(env(t));
  assert.equal(auditCount(t), AUDIT_KEEP, "the ledger is still unbounded on Cloudflare");
  t.close();
});

await check("it keeps the NEWEST 300 — an audit ledger nobody can read back is not evidence", async () => {
  const t = openTestD1();
  seedAudit(t, AUDIT_KEEP + 120);
  await runCron(env(t));
  const oldest = t.query<{ created: string }>(
    "SELECT created FROM agent_llm_audit ORDER BY created ASC LIMIT 1")[0].created;
  const all = t.query<{ created: string }>("SELECT created FROM agent_llm_audit");
  assert.equal(all.length, AUDIT_KEEP);
  const dropped = t.query<{ n: number }>(
    "SELECT COUNT(*) AS n FROM agent_llm_audit WHERE created < ?", oldest)[0].n;
  assert.equal(dropped, 0);
  t.close();
});

await check("a ledger already under the cap is left alone", async () => {
  const t = openTestD1();
  seedAudit(t, 12);
  await runCron(env(t));
  assert.equal(auditCount(t), 12);
  t.close();
});

// ---------------------------------------------------------------------------
// Evidence: two ceilings, and the bytes
// ---------------------------------------------------------------------------

await check("no owner keeps more than 20 receipt photos — the privacy half", async () => {
  const t = openTestD1();
  const r2 = fakeR2();
  seedEvidence(t, r2, "owner00000quiet", 31);
  await runCron(env(t, r2));
  const mine = t.query<{ n: number }>(
    "SELECT COUNT(*) AS n FROM evidence WHERE owner_ref = ?", "owner00000quiet")[0].n;
  assert.equal(mine, EVIDENCE_PER_OWNER, "one owner's screenshots accumulated past the cap");
  t.close();
});

await check("the pruned rows take their R2 objects with them", async () => {
  const t = openTestD1();
  const r2 = fakeR2();
  const ids = seedEvidence(t, r2, "owner00000quiet", 31);
  assert.equal(r2.objects.size, 31);
  await runCron(env(t, r2));
  assert.equal(r2.objects.size, EVIDENCE_PER_OWNER,
    "bytes were left in R2 for rows that no longer exist — a paid-for object "
    + "no row can ever name again");
  // Every surviving row still has its bytes: this is the half that matters to
  // an owner, and deleting an object whose row survived is a 404 on a live
  // receipt.
  for (const row of t.query<{ id: string; image: string }>("SELECT id, image FROM evidence")) {
    assert.ok(r2.objects.has(`evidence/${row.id}/${row.image}`),
      `a surviving evidence row lost its bytes: ${row.id}`);
  }
  // And the deletes named the right keys.
  for (const id of ids.slice(0, 11)) {
    assert.ok(r2.deleted.includes(`evidence/${id}/receipt.jpg`), `not deleted: ${id}`);
  }
  t.close();
});

await check("the global ceiling of 60 holds across owners", async () => {
  const t = openTestD1();
  const r2 = fakeR2();
  // Five owners, 18 each: nobody trips the per-owner cap, but 90 > 60.
  for (let o = 0; o < 5; o++) seedEvidence(t, r2, `owner0000000o${o}`, 18, o * 100);
  assert.equal(evidenceCount(t), 90);
  await runCron(env(t, r2));
  assert.equal(evidenceCount(t), EVIDENCE_TOTAL, "the disk half of the ceiling did not fire");
  assert.equal(r2.objects.size, EVIDENCE_TOTAL);
  t.close();
});

await check("a bucket that refuses the delete loses the bytes, never the rows", async () => {
  // R2 being unreachable must not leave the table uncapped: the row half is
  // what bounds the database, and the orphaned objects are named in the log.
  const t = openTestD1();
  const r2 = fakeR2();
  seedEvidence(t, r2, "owner00000quiet", 31);
  r2.bucket.delete = (async () => { throw new Error("R2 is unreachable"); }) as R2Bucket["delete"];
  logs.length = 0;
  await runCron(env(t, r2));
  const mine = t.query<{ n: number }>("SELECT COUNT(*) AS n FROM evidence")[0].n;
  assert.equal(mine, EVIDENCE_PER_OWNER);
  assert.ok(logs.some((l) => l.includes("object(s) remain in R2")),
    "the orphaned objects were not named in the log: " + JSON.stringify(logs));
  t.close();
});

await check("no bucket bound: the rows are still capped and the log says what was left behind", async () => {
  const t = openTestD1();
  const r2 = fakeR2();
  seedEvidence(t, r2, "owner00000quiet", 31);
  logs.length = 0;
  await runCron(env(t));                    // no EVIDENCE binding at all
  assert.equal(evidenceCount(t), EVIDENCE_PER_OWNER);
  assert.ok(logs.some((l) => l.includes("no bucket is bound")), JSON.stringify(logs));
  t.close();
});

await check("a fleet under both ceilings is left entirely alone", async () => {
  const t = openTestD1();
  const r2 = fakeR2();
  seedEvidence(t, r2, "owner0000000o1", 5);
  seedEvidence(t, r2, "owner0000000o2", 5, 100);
  await runCron(env(t, r2));
  assert.equal(evidenceCount(t), 10);
  assert.equal(r2.objects.size, 10);
  assert.deepEqual(r2.deleted, []);
  t.close();
});

// ---------------------------------------------------------------------------
// The dispatch itself
// ---------------------------------------------------------------------------

await check("the sweeps hang off the DAILY cron, not the five-minute one", async () => {
  // The */5 tick sends texts; hanging a table scan off it would put the
  // retention read on every reminder pass.
  const t = openTestD1();
  const r2 = fakeR2();
  seedAudit(t, AUDIT_KEEP + 120);
  seedEvidence(t, r2, "owner00000quiet", 31);
  await runCron(env(t, r2), "*/5 * * * *");
  assert.equal(auditCount(t), AUDIT_KEEP + 120, "the audit sweep ran on the five-minute tick");
  assert.equal(evidenceCount(t), 31);
  await runCron(env(t, r2), PRUNE_CRON);
  assert.equal(auditCount(t), AUDIT_KEEP);
  assert.equal(evidenceCount(t), EVIDENCE_PER_OWNER);
  t.close();
});

await check("the prune's original four tables still get pruned", async () => {
  // The retention sweeps were appended to an existing job; the job's own work
  // must be untouched by them.
  const t = openTestD1();
  const old = "2026-01-01 00:00:00.000Z";
  t.exec(`INSERT INTO internal_activity (id, created, actor, actor_name, action, subject, verb, ref)
          VALUES ('act000000000001', '${old}', '', 'HQ', 'did', 'thing', '', '')`);
  t.exec(`INSERT INTO internal_notifs (id, created, person, kind, text, read)
          VALUES ('ntf000000000001', '${old}', 'p1', 'done', 'seen', 1)`);
  await runCron(env(t));
  assert.equal(t.query<{ n: number }>("SELECT COUNT(*) AS n FROM internal_activity")[0].n, 0);
  assert.equal(t.query<{ n: number }>("SELECT COUNT(*) AS n FROM internal_notifs")[0].n, 0);
  t.close();
});

console.log = realLog;
console.log(`cron-retention: ${passes} checks passed, ${failures} failed`);
if (failures) process.exit(1);
