import assert from "node:assert/strict";
import { FakeD1, asD1 } from "../../test/fake-d1.ts";
import { OwnerLifecycle } from "../src/owner_lifecycle.ts";
import { drainMemoryPurges, type PurgeEnv } from "../src/purge.ts";

const A = "auditowner00001", B = "auditowner00002";
let passes = 0;
let failures = 0;
async function check(name: string, fn: () => Promise<void>) {
  try { await fn(); passes++; console.log("PASS " + name); }
  catch (error) { failures++; console.error("FAIL " + name + ": " + (error as Error).message); }
}
function state() {
  const map = new Map<string, unknown>();
  return { async get<T>(key: string) { return map.get(key) as T | undefined; },
           async put(key: string, value: unknown) { map.set(key, value); } };
}
function bucket(initial: string[]) {
  const keys = new Set(initial);
  let fail = false;
  const port = {
    async list(options: {prefix: string; cursor?: string; limit?: number}) {
      if (fail) throw new Error("R2 unavailable");
      const found = [...keys].sort().filter((key) => key.startsWith(options.prefix)
        && (!options.cursor || key > options.cursor));
      const slice = found.slice(0, Math.min(2, options.limit ?? 2));
      return { objects: slice.map((key) => ({key})), truncated: slice.length < found.length,
               cursor: slice[slice.length - 1] };
    },
    async delete(input: string | string[]) {
      if (fail) throw new Error("R2 unavailable");
      for (const key of typeof input === "string" ? [input] : input) keys.delete(key);
    },
  };
  return { keys, port: port as unknown as R2Bucket, fail: (value: boolean) => { fail = value; } };
}
function rig() {
  const db = new FakeD1();
  db.db.prepare("INSERT INTO owners (id,email,tokenKey) VALUES (?,?,?)").run(B, "b@test.invalid", "b-key");
  for (const ref of [A, B]) db.db.prepare(
    "INSERT INTO purges (id,owner_ref,requested_at,memory_purged) VALUES (?,?,?,0)",
  ).run("purge-" + ref, ref, "2026-09-07T00:00:00Z");
  const current = bucket(["memory.db", "clock_state.json", "extra.snapshot"].map((name) => `owners/${A}/${name}`)
    .concat([`owners/${B}/memory.db`, `owners/${A}suffix/memory.db`]));
  const archive = bucket([`worker/${A}/one.zip`, `worker/${A}/two.zip`, `worker/${A}/three.zip`, `worker/${B}/one.zip`]);
  const env = { DB: asD1(db), OWNER_STATE: current.port, STATE_ARCHIVE: archive.port } as PurgeEnv;
  return { db, current, archive, env };
}

await check("closed owner is killed before paginated state/archive removal; a live owner survives", async () => {
  const r = rig();
  const stopped: string[] = [];
  const result = await drainMemoryPurges(r.env, async (ref) => {
    assert.ok(r.current.keys.has(`owners/${A}/memory.db`), "kill must precede object deletion");
    stopped.push(ref);
  });
  assert.deepEqual(result, { purged: 1, failed: 0 });
  assert.deepEqual(stopped, [A]);
  assert.deepEqual([...r.current.keys].sort(), [`owners/${A}suffix/memory.db`, `owners/${B}/memory.db`].sort());
  assert.deepEqual([...r.archive.keys], [`worker/${B}/one.zip`]);
  assert.equal(r.db.rows<{memory_purged:number}>("SELECT memory_purged FROM purges WHERE owner_ref = ?", A)[0].memory_purged, 1);
  assert.equal(r.db.rows<{memory_purged:number}>("SELECT memory_purged FROM purges WHERE owner_ref = ?", B)[0].memory_purged, 0);
});

await check("a failed container stop cannot be called a completed purge", async () => {
  const r = rig();
  assert.deepEqual(await drainMemoryPurges(r.env, async () => { throw new Error("container still running"); }),
    { purged: 0, failed: 1 });
  assert.ok(r.current.keys.has(`owners/${A}/memory.db`));
  assert.equal(r.db.rows<{memory_purged:number}>("SELECT memory_purged FROM purges WHERE owner_ref = ?", A)[0].memory_purged, 0);
});

await check("an archive failure remains pending and a later retry finishes", async () => {
  const r = rig();
  r.archive.fail(true);
  assert.deepEqual(await drainMemoryPurges(r.env, async () => {}), { purged: 0, failed: 1 });
  assert.equal(r.db.rows<{memory_purged:number}>("SELECT memory_purged FROM purges WHERE owner_ref = ?", A)[0].memory_purged, 0);
  r.archive.fail(false);
  assert.deepEqual(await drainMemoryPurges(r.env, async () => {}), { purged: 1, failed: 0 });
});

await check("a bucket returning another owner's key is refused before deleting it", async () => {
  const r = rig();
  let removed = false;
  r.env.OWNER_STATE = { async list() { return { objects: [{key:`owners/${B}/memory.db`}], truncated:false }; },
    async delete() { removed = true; } } as unknown as R2Bucket;
  assert.deepEqual(await drainMemoryPurges(r.env, async () => {}), { purged: 0, failed: 1 });
  assert.equal(removed, false);
});

await check("deletion waits for an in-flight start, kills it, and prevents a later restart", async () => {
  const storage = state();
  let exists = true;
  const events: string[] = [];
  let release!: () => void;
  let started!: () => void;
  const entered = new Promise<void>((resolve) => { started = resolve; });
  const pending = new Promise<void>((resolve) => { release = resolve; });
  const lifecycle = new OwnerLifecycle(storage, async () => exists, async () => {
    events.push("starting"); started(); await pending; events.push("started");
  }, async () => { events.push("killed"); });
  const first = lifecycle.ensure({ id: A, legacy_uuid: "" });
  await entered;
  exists = false;
  const erase = lifecycle.erase(A);
  release();
  await Promise.all([first, erase]);
  assert.deepEqual(events, ["starting", "started", "killed"]);
  exists = true; // even an erroneous recreation of the old ID cannot revive it
  await assert.rejects(() => lifecycle.ensure({ id: A, legacy_uuid: "" }));
  const afterRestart = new OwnerLifecycle(storage, async () => true,
    async () => { throw new Error("must never start"); }, async () => {});
  await assert.rejects(() => afterRestart.ensure({ id: A, legacy_uuid: "" }));
});

await check("a failed start does not poison the queue and a failed kill remains retryable", async () => {
  const storage = state();
  let exists = true, kills = 0;
  const lifecycle = new OwnerLifecycle(storage, async () => exists,
    async () => { throw new Error("start failed"); }, async () => {
      if (++kills === 1) throw new Error("kill failed");
    });
  await assert.rejects(() => lifecycle.ensure({ id: A, legacy_uuid: "" }));
  exists = false;
  await assert.rejects(() => lifecycle.erase(A));
  assert.equal(await storage.get<boolean>("account_erased"), true);
  await lifecycle.erase(A);
  assert.equal(kills, 2);
});

await check("a living owner cannot be erased, including through a stale purge request", async () => {
  let killed = false;
  const lifecycle = new OwnerLifecycle(state(), async () => true, async () => {}, async () => { killed = true; });
  await assert.rejects(() => lifecycle.erase(A));
  assert.equal(killed, false);
});

await check("shared historical archives prevent a false complete-erasure verdict", async () => {
  const r = rig();
  r.archive.keys.add("worker/state-legacy.zip");
  assert.deepEqual(await drainMemoryPurges(r.env, async () => {}), { purged: 0, failed: 1 });
  assert.ok(r.archive.keys.has("worker/state-legacy.zip"), "another person's shared archive must not be discarded");
  assert.equal(r.db.rows<{ memory_purged: number }>("SELECT memory_purged FROM purges WHERE owner_ref=?", A)[0].memory_purged, 0);
});

console.log(`brain erasure: ${passes} passed, ${failures} failed`);
if (failures) process.exit(1);
