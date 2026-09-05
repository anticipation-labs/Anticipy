/**
 * Runs with no network and no D1 (an in-process SQLite one carrying the real
 * migration/d1/schema.sql, index and all):
 *
 *   node --experimental-strip-types migration/workers/test/records-commitment.test.ts
 *
 * THE TRAP THIS PINS (audit F15). `idx_jobs_active_commitment` is UNIQUE over
 * every jobs row whose `commitment_key` is not empty — the only thing stopping
 * two processes both reading "no active promise" and both minting one.
 * PocketBase kept it honest with a model hook
 * (backend/pb_hooks/job_commitment_identity.pb.js): a row going terminal
 * releases its key. The Worker had no equivalent, so on Cloudflare every
 * finished row held its key forever and the NEXT mint for the same promise
 * collided with a corpse: 400, the brain's handler searches only ACTIVE
 * statuses, finds nothing, returns QUEUE_WRITE_FAILED, and hear() drops the
 * goal. Every clock window, silently, forever.
 *
 * These checks go through records.create / records.update — the real writers —
 * and let SQLite's own index deliver the verdict. A fake that recorded SQL
 * strings could not tell you the trap was disarmed; a second create with the
 * same key can.
 *
 * MUTATIONS THIS FILE MUST GO RED ON: the release deleted from update (the
 * shipped defect); the release deleted from create; the terminal list narrowed
 * (e.g. `failed` dropped, which is the deterministic re-mint path); the
 * polarity inverted so an ACTIVE status releases the key instead.
 */
import assert from "node:assert/strict";
import { create, update, releasesCommitment, type RecordsRequest } from "../src/pb/records.ts";
import { COLLECTIONS } from "../src/pb/schema.ts";
import { openTestD1, type TestDb } from "./sqlite-d1.ts";

let failures = 0;
let passes = 0;
async function check(what: string, fn: () => void | Promise<void>): Promise<void> {
  try { await fn(); passes++; }
  catch (err) { failures++; console.error("FAIL " + what + "\n     " + (err as Error).message); }
}

const OWNER = "owner000000one1";
const KEY = "d4c3b2a1".repeat(8);   // sha256-shaped, as anticipy_core mints it

function req(o: Partial<RecordsRequest> & { collection: string }): RecordsRequest {
  const def = COLLECTIONS[o.collection];
  return {
    collection: def, recordId: null, method: "POST",
    url: new URL("https://api.anticipy.ai/api/collections/" + o.collection + "/records"),
    body: null, principal: { kind: "service" }, forcedScope: null, extraAst: null,
    ...o, collection: def,
  } as RecordsRequest;
}

function job(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    goal: "book the table", status: "queued", owner_ref: OWNER,
    device_id: "brain", ...over,
  };
}

async function post(t: TestDb, body: Record<string, unknown>): Promise<Response> {
  return create({ DB: t.db }, req({ collection: "jobs", method: "POST", body }));
}
async function patch(t: TestDb, id: string, body: Record<string, unknown>): Promise<Response> {
  return update({ DB: t.db }, req({ collection: "jobs", method: "PATCH", recordId: id, body }));
}
const keyOf = (t: TestDb, id: string) =>
  t.query<{ commitment_key: string }>("SELECT commitment_key FROM jobs WHERE id = ?", id)[0]?.commitment_key;

// ---------------------------------------------------------------------------
// The trap, and that it is now disarmed. This is the whole finding in four
// steps, driven through the real writers against the real index.
// ---------------------------------------------------------------------------

await check("a job that FINISHES releases its commitment key, so the promise can be minted again", async () => {
  const t = openTestD1();
  const first = await post(t, job({ commitment_key: KEY }));
  const created = await first.json() as { id: string };
  assert.equal(first.status, 200, JSON.stringify(created));
  const id = created.id;
  assert.equal(keyOf(t, id), KEY, "the live row must HOLD the key — that is the lock");

  // The brain marks it done. It sends status and nothing about the key: it has
  // no idea the column exists.
  const done = await patch(t, id, { status: "done" });
  assert.equal(done.status, 200, JSON.stringify(await done.json()));
  assert.equal(keyOf(t, id), "", "a done row still holds the key");

  // THE VERDICT COMES FROM THE INDEX, not from us: the same promise mints again.
  const again = await post(t, job({ commitment_key: KEY }));
  assert.equal(again.status, 200,
    "the re-mint was refused, so the corpse still owns the promise: "
    + JSON.stringify(await again.json()));
  t.close();
});

await check("a FAILED job releases it too — the deterministic re-mint path", async () => {
  // brain/anticipy_core.py:5313,5333-5347: only done/cancelled resolve the
  // memory node, so after a FAILED run the node stays open and the clock's
  // initiative re-mints the SAME key on the next window. This is the leg that
  // repeats forever when it is wrong.
  const t = openTestD1();
  const id = (await (await post(t, job({ commitment_key: KEY }))).json() as { id: string }).id;
  await patch(t, id, { status: "failed", result: "the site refused" });
  assert.equal(keyOf(t, id), "");
  const retry = await post(t, job({ commitment_key: KEY }));
  assert.equal(retry.status, 200,
    "the clock's retry was refused: " + JSON.stringify(await retry.json()));
  t.close();
});

await check("a CANCELLED job releases it", async () => {
  const t = openTestD1();
  const id = (await (await post(t, job({ commitment_key: KEY }))).json() as { id: string }).id;
  await patch(t, id, { status: "cancelled" });
  assert.equal(keyOf(t, id), "");
  t.close();
});

await check("a row BORN terminal is not born holding the key", async () => {
  // A legacy row with no workflow_id skips workflow_guard entirely, so its
  // ENTRY_STATUSES rule does not cover this.
  const t = openTestD1();
  const born = await post(t, job({ status: "cancelled", commitment_key: KEY }));
  const bornRow = await born.json() as { id: string };
  assert.equal(born.status, 200, JSON.stringify(bornRow));
  assert.equal(keyOf(t, bornRow.id), "");
  const fresh = await post(t, job({ commitment_key: KEY }));
  assert.equal(fresh.status, 200, JSON.stringify(await fresh.json()));
  t.close();
});

// ---------------------------------------------------------------------------
// The lock still locks. A release that fired one status too early would be a
// worse defect than the one being fixed: two live workflows for one promise.
// ---------------------------------------------------------------------------

await check("a LIVE job keeps its key: two live rows for one promise are still refused", async () => {
  const t = openTestD1();
  const id = (await (await post(t, job({ commitment_key: KEY }))).json() as { id: string }).id;

  for (const status of ["running", "needs_user", "awaiting_confirm", "queued"]) {
    await patch(t, id, { status });
    assert.equal(keyOf(t, id), KEY, `a ${status} row lost its commitment key`);
  }

  const second = await post(t, job({ commitment_key: KEY }));
  assert.equal(second.status, 400, "a second LIVE row took the same promise");
  const body = await second.json() as { data: Record<string, { code: string }> };
  // The shape brain/worker.py's reserve_uninvited_text reads: a 400 naming the
  // column means "taken, read it back"; anything else means "do not act".
  assert.equal(body.data.commitment_key.code, "validation_not_unique");
  t.close();
});

await check("a PATCH that names no status leaves the key exactly as it was", async () => {
  // The common write. An update that touched the key here would release the
  // lock on every trace append.
  const t = openTestD1();
  const id = (await (await post(t, job({ commitment_key: KEY }))).json() as { id: string }).id;
  const res = await patch(t, id, { trace: "step 1" });
  assert.equal(res.status, 200);
  assert.equal(keyOf(t, id), KEY);
  t.close();
});

await check("an unkeyed job is untouched by any of this", async () => {
  const t = openTestD1();
  const id = (await (await post(t, job())).json() as { id: string }).id;
  await patch(t, id, { status: "done" });
  assert.equal(keyOf(t, id), "");
  // Many terminal rows with no key at all: the partial index ignores them.
  for (let i = 0; i < 3; i++) {
    const r = await post(t, job({ status: "done" }));
    assert.equal(r.status, 200, JSON.stringify(await r.json()));
  }
  t.close();
});

await check("only jobs are affected — no other collection has a commitment", async () => {
  const t = openTestD1();
  assert.equal(releasesCommitment(COLLECTIONS.jobs, { status: "done" }), true);
  assert.equal(releasesCommitment(COLLECTIONS.events, { status: "done" }), false);
  assert.equal(releasesCommitment(COLLECTIONS.evidence, { status: "done" }), false);
  // And an events write with a `status`-shaped body is not even a known field.
  const res = await create({ DB: t.db }, req({
    collection: "events", method: "POST",
    body: { kind: "transcript", text: "hello", owner_ref: OWNER, device_id: "iphone-b124" },
  }));
  assert.equal(res.status, 200, JSON.stringify(await res.json()));
  t.close();
});

await check("the whole live-release SELECT the integrator runs reads zero after this", async () => {
  // The exact predicate in the F15 report, over rows written the way the brain
  // writes them. It is the shape of the gate leg that closes this against LIVE.
  const t = openTestD1();
  const keys = ["k1", "k2", "k3"].map((k) => k.padEnd(64, "0"));
  const ids: string[] = [];
  for (const k of keys) {
    ids.push((await (await post(t, job({ commitment_key: k }))).json() as { id: string }).id);
  }
  await patch(t, ids[0], { status: "done" });
  await patch(t, ids[1], { status: "failed" });
  await patch(t, ids[2], { status: "cancelled" });
  const left = t.query<{ n: number }>(
    `SELECT COUNT(*) AS n FROM jobs
      WHERE status IN ('done','failed','cancelled') AND commitment_key != ''`)[0].n;
  assert.equal(left, 0, "terminal rows are still holding commitment keys");
  t.close();
});

console.log(`records-commitment: ${passes} checks passed, ${failures} failed`);
if (failures) process.exit(1);
