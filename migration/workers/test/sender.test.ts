/**
 * Runs with no dependencies, no network and no D1:
 *
 *   node --experimental-strip-types migration/workers/test/sender.test.ts
 *
 * The pure half of src/pb/sender.ts, pinned to backend/pb_hooks/sms.pb.js
 * :160-293 (the oracle): who a phone number resolves to, and what row a
 * resolved text becomes. The wire half -- the two carriers' front doors, a
 * real workerd, a real D1 with the partial-unique index -- is
 * migration/spec/contract_tests.py (TestSendblueInbound, TestSmsInbound) run
 * by scripts/sms_contract_local.sh.
 *
 * MUTATIONS THIS FILE MUST GO RED ON: an ambiguous number resolved to the
 * first owner; an unknown (thrown) read treated as "nobody"; the seed in
 * owners.phone admitted for an account that has a profile; a stale profile
 * row treated as current authority; the events row missing a field the brain
 * reads.
 */
import assert from "node:assert/strict";
import {
  resolveSenderWith, landInboundText, recordInboundReply, type SenderDb,
} from "../src/pb/sender.ts";

let failures = 0;
let passes = 0;
async function check(what: string, fn: () => void | Promise<void>): Promise<void> {
  try { await fn(); passes++; }
  catch (err) { failures++; console.error("FAIL " + what + "\n     " + (err as Error).message); }
}

// ---------------------------------------------------------------------------
// A fake of the three reads. `throwOn` makes one of them fail, the way a D1
// read fails: the oracle's routingUnknown.
// ---------------------------------------------------------------------------
interface Profile { owner_ref: string; phone: string; updated: string }
interface Owner { id: string; phone: string }
function fakeDb(o: { profiles?: Profile[]; owners?: Owner[]; throwOn?: keyof SenderDb }): SenderDb {
  const profiles = o.profiles ?? [];
  const owners = o.owners ?? [];
  const boom = (name: keyof SenderDb) => { if (o.throwOn === name) throw new Error("D1_ERROR: " + name); };
  return {
    async profileOwnerRefsByPhone(phone) {
      boom("profileOwnerRefsByPhone");
      return profiles.filter((p) => p.phone === phone && p.owner_ref).map((p) => p.owner_ref);
    },
    async currentProfilePhone(ref) {
      boom("currentProfilePhone");
      const mine = profiles.filter((p) => p.owner_ref === ref).sort((a, b) => b.updated.localeCompare(a.updated));
      return mine.length ? mine[0].phone : null;
    },
    async ownerIdsByPhone(phone) {
      boom("ownerIdsByPhone");
      return owners.filter((w) => w.phone === phone).map((w) => w.id);
    },
  };
}
const P = "+15550100001";

await check("one profile carrying the number resolves to its owner", async () => {
  const db = fakeDb({ profiles: [{ owner_ref: "o1", phone: P, updated: "2026-09-01" }] });
  assert.deepEqual(await resolveSenderWith(db, P), { kind: "owner", owner_ref: "o1" });
});

await check("a stale profile whose CURRENT row no longer carries the number is nobody", async () => {
  // sms.pb.js:181-186: a phone match on an old duplicate profile is not current authority.
  const db = fakeDb({ profiles: [
    { owner_ref: "o1", phone: P, updated: "2026-01-01" },
    { owner_ref: "o1", phone: "", updated: "2026-02-01" },
  ] });
  assert.deepEqual(await resolveSenderWith(db, P), { kind: "none" });
});

await check("a stale profile beside a current one with a DIFFERENT number is nobody too", async () => {
  const db = fakeDb({ profiles: [
    { owner_ref: "o1", phone: P, updated: "2026-01-01" },
    { owner_ref: "o1", phone: "+15550100777", updated: "2026-02-01" },
  ] });
  assert.deepEqual(await resolveSenderWith(db, P), { kind: "none" });
});

await check("owners.phone is the fallback for an account with NO profile row", async () => {
  const db = fakeDb({ owners: [{ id: "o2", phone: P }] });
  assert.deepEqual(await resolveSenderWith(db, P), { kind: "owner", owner_ref: "o2" });
});

await check("owners.phone is NOT admitted once the account has any profile row — the profile is canonical", async () => {
  // sms.pb.js:215-221: admitting the seed would re-affiliate a number the person removed.
  const db = fakeDb({
    owners: [{ id: "o2", phone: P }],
    profiles: [{ owner_ref: "o2", phone: "", updated: "2026-02-01" }],
  });
  assert.deepEqual(await resolveSenderWith(db, P), { kind: "none" });
});

await check("two profiles carrying the number are AMBIGUOUS, never the first one", async () => {
  const db = fakeDb({ profiles: [
    { owner_ref: "o1", phone: P, updated: "2026-09-02" },
    { owner_ref: "o2", phone: P, updated: "2026-09-01" },
  ] });
  const who = await resolveSenderWith(db, P);
  assert.equal(who.kind, "ambiguous", "resolved a shared number to " + JSON.stringify(who));
  assert.equal((who as { count: number }).count, 2);
});

await check("a profile owner AND a seed-only owner on the same number are ambiguous — the halves are unioned", async () => {
  // sms.pb.js:197-203: considering the seed only when profiles found nobody
  // would silently route B's text to A.
  const db = fakeDb({
    profiles: [{ owner_ref: "o1", phone: P, updated: "2026-09-01" }],
    owners: [{ id: "o2", phone: P }],
  });
  assert.equal((await resolveSenderWith(db, P)).kind, "ambiguous");
});

await check("the same account found by both halves is ONE match, not two", async () => {
  const db = fakeDb({
    profiles: [{ owner_ref: "o1", phone: P, updated: "2026-09-01" }],
    owners: [{ id: "o1", phone: P }],
  });
  // o1 has a profile, so the seed half does not admit it; and even if it did,
  // a Set holds one o1. Either way: one owner.
  assert.deepEqual(await resolveSenderWith(db, P), { kind: "owner", owner_ref: "o1" });
});

await check("a thrown profile query is UNKNOWN, not nobody", async () => {
  const db = fakeDb({ owners: [{ id: "o2", phone: P }], throwOn: "profileOwnerRefsByPhone" });
  assert.deepEqual(await resolveSenderWith(db, P), { kind: "unknown" });
});

await check("a thrown canonical re-read is UNKNOWN even when the other half found exactly one", async () => {
  // sms.pb.js:265-269: a partial candidate set is never safe enough, even at one row.
  const db = fakeDb({ profiles: [{ owner_ref: "o1", phone: P, updated: "2026-09-01" }], throwOn: "currentProfilePhone" });
  assert.deepEqual(await resolveSenderWith(db, P), { kind: "unknown" });
});

await check("a thrown owners query is UNKNOWN even when a profile matched cleanly", async () => {
  const db = fakeDb({ profiles: [{ owner_ref: "o1", phone: P, updated: "2026-09-01" }], throwOn: "ownerIdsByPhone" });
  assert.deepEqual(await resolveSenderWith(db, P), { kind: "unknown" });
});

await check("a blank number is nobody, and reads nothing", async () => {
  const db = fakeDb({ throwOn: "profileOwnerRefsByPhone" });
  assert.deepEqual(await resolveSenderWith(db, "  "), { kind: "none" });
});

await check("the canonical re-read trims the stored number, as the oracle trims (sms.pb.js:184)", async () => {
  // The candidate is found by exact phone (row 1); the NEWEST row carries the
  // same number with padding, and the re-read compares it trimmed.
  const db = fakeDb({ profiles: [
    { owner_ref: "o1", phone: P, updated: "2026-01-01" },
    { owner_ref: "o1", phone: " " + P + " ", updated: "2026-02-01" },
  ] });
  assert.deepEqual(await resolveSenderWith(db, P), { kind: "owner", owner_ref: "o1" });
});

await check("whitespace around the SENDER's number is trimmed before the lookup", async () => {
  const db = fakeDb({ profiles: [{ owner_ref: "o1", phone: P, updated: "2026-09-01" }] });
  assert.deepEqual(await resolveSenderWith(db, " " + P + "\n"), { kind: "owner", owner_ref: "o1" });
});

await check("an empty owner_ref on a profile row is never a candidate", async () => {
  const db = fakeDb({ profiles: [{ owner_ref: "", phone: P, updated: "2026-09-01" }] });
  assert.deepEqual(await resolveSenderWith(db, P), { kind: "none" });
});

// ---------------------------------------------------------------------------
// The row. A fake D1 that answers the four statements records.create() and
// the resolver issue, and records the INSERT.
// ---------------------------------------------------------------------------
const LIVE_EVENTS_COLUMNS = [
  "id", "created", "updated", "device_id", "kind", "text", "decision", "goal",
  "needs_confirmation", "source", "seq", "owner_ref", "external_event_id", "importance",
];
interface Inserted { cols: string[]; vals: unknown[] }
function fakeD1(o: {
  profiles?: Profile[]; owners?: Owner[];
  insertError?: string; selectError?: boolean;
}): { db: D1Database; inserts: Inserted[] } {
  const inserts: Inserted[] = [];
  const sender = fakeDb({ profiles: o.profiles, owners: o.owners });
  const stmt = (sql: string) => ({
    bind: (...vals: unknown[]) => ({
      async all() {
        if (sql.startsWith("SELECT name FROM pragma_table_info")) {
          return { results: LIVE_EVENTS_COLUMNS.map((name) => ({ name })) };
        }
        if (o.selectError) throw new Error("D1_ERROR: storage failure");
        if (sql.includes('FROM "owner_profile" WHERE "phone"')) {
          return { results: (await sender.profileOwnerRefsByPhone(String(vals[0]))).map((owner_ref) => ({ owner_ref })) };
        }
        if (sql.includes('FROM "owners" WHERE "phone"')) {
          return { results: (await sender.ownerIdsByPhone(String(vals[0]))).map((id) => ({ id })) };
        }
        throw new Error("fake D1: unexpected all(): " + sql);
      },
      async first() {
        if (o.selectError) throw new Error("D1_ERROR: storage failure");
        if (sql.includes('FROM "owner_profile" WHERE "owner_ref"')) {
          const phone = await sender.currentProfilePhone(String(vals[0]));
          return phone === null ? null : { phone };
        }
        if (sql.startsWith('SELECT * FROM "events"')) {
          const last = inserts[inserts.length - 1];
          const row: Record<string, unknown> = {};
          last.cols.forEach((c, i) => { row[c] = last.vals[i]; });
          return row;
        }
        throw new Error("fake D1: unexpected first(): " + sql);
      },
      async run() {
        if (sql.startsWith('INSERT INTO "events"')) {
          if (o.insertError) throw new Error(o.insertError);
          const cols = sql.slice(sql.indexOf("(") + 1, sql.indexOf(")")).split(",").map((c) => c.trim().replace(/"/g, ""));
          inserts.push({ cols, vals });
          return { meta: { changes: 1 } };
        }
        throw new Error("fake D1: unexpected run(): " + sql);
      },
    }),
  });
  const db = { prepare: stmt } as unknown as D1Database;
  return { db, inserts };
}
const rowOf = (ins: Inserted): Record<string, unknown> => {
  const row: Record<string, unknown> = {};
  ins.cols.forEach((c, i) => { row[c] = ins.vals[i]; });
  return row;
};
const SID = "SM" + "a".repeat(32);

await check("a known owner's text becomes the oracle's row, exactly (sms.pb.js:280-288)", async () => {
  const { db, inserts } = fakeD1({ profiles: [{ owner_ref: "o1", phone: P, updated: "2026-09-01" }] });
  const landed = await landInboundText({ DB: db }, "sms/test", "MessageSid", { from: P, text: "  yes  ", externalId: SID });
  assert.equal(landed.kind, "written", JSON.stringify(landed));
  assert.equal(inserts.length, 1);
  const row = rowOf(inserts[0]);
  assert.equal(row.device_id, "sms");
  assert.equal(row.kind, "sms_reply");
  assert.equal(row.text, "yes", "trimmed, as the oracle trims Body");
  assert.equal(row.decision, "", "the brain's poll filters on decision=\"\"; NULL here was deaf ears");
  assert.equal(row.goal, P, "goal is the sender's number; the worker replies to it");
  assert.equal(row.owner_ref, "o1");
  assert.equal(row.external_event_id, SID);
  assert.match(String(row.id), /^[a-z0-9]{15}$/, "a PocketBase-shaped id");
  assert.match(String(row.created), /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}Z$/, "PocketBase autodate shape");
  assert.equal(row.updated, row.created);
  // fillEmpties ran: the columns the body omits carry the empty, not NULL.
  assert.equal(row.source, "");
  assert.equal(row.seq, 0);
  assert.equal(row.needs_confirmation, 0, "bool -> 0/1 in D1");
});

await check("a collision on external_event_id is 'already handled' — the carrier's retry is one command", async () => {
  const { db, inserts } = fakeD1({
    profiles: [{ owner_ref: "o1", phone: P, updated: "2026-09-01" }],
    insertError: "D1_ERROR: UNIQUE constraint failed: events.external_event_id: SQLITE_CONSTRAINT",
  });
  const landed = await landInboundText({ DB: db }, "sms/test", "MessageSid", { from: P, text: "yes", externalId: SID });
  assert.deepEqual(landed, { kind: "already_handled" });
  assert.equal(inserts.length, 0);
});

await check("any other write failure is 'failed' (a 500, so the carrier retries), never a 200", async () => {
  const { db } = fakeD1({
    profiles: [{ owner_ref: "o1", phone: P, updated: "2026-09-01" }],
    insertError: "D1_ERROR: database is locked",
  });
  const landed = await landInboundText({ DB: db }, "sms/test", "MessageSid", { from: P, text: "yes", externalId: SID });
  assert.equal(landed.kind, "failed", JSON.stringify(landed));
});

await check("an ambiguous number is dropped and NOTHING is inserted", async () => {
  const { db, inserts } = fakeD1({ profiles: [
    { owner_ref: "o1", phone: P, updated: "2026-09-02" },
    { owner_ref: "o2", phone: P, updated: "2026-09-01" },
  ] });
  const landed = await landInboundText({ DB: db }, "sms/test", "MessageSid", { from: P, text: "yes", externalId: SID });
  assert.deepEqual(landed, { kind: "dropped", why: "ambiguous" });
  assert.equal(inserts.length, 0, "an ambiguous text must never pick whose browser to drive");
});

await check("an unrecognised number is dropped and nothing is inserted", async () => {
  const { db, inserts } = fakeD1({});
  const landed = await landInboundText({ DB: db }, "sms/test", "MessageSid", { from: P, text: "yes", externalId: SID });
  assert.deepEqual(landed, { kind: "dropped", why: "no_owner" });
  assert.equal(inserts.length, 0);
});

await check("a failed read is UNKNOWN and nothing is inserted", async () => {
  const { db, inserts } = fakeD1({ selectError: true });
  const landed = await landInboundText({ DB: db }, "sms/test", "MessageSid", { from: P, text: "yes", externalId: SID });
  assert.deepEqual(landed, { kind: "unknown" });
  assert.equal(inserts.length, 0);
});

await check("a blank text is dropped before any read", async () => {
  const { db, inserts } = fakeD1({ selectError: true });
  const landed = await landInboundText({ DB: db }, "sms/test", "MessageSid", { from: P, text: "   ", externalId: SID });
  assert.deepEqual(landed, { kind: "dropped", why: "empty" });
  assert.equal(inserts.length, 0);
});

await check("recordInboundReply reports the duplicate under PocketBase's own 400 shape", async () => {
  const { db } = fakeD1({ insertError: "D1_ERROR: UNIQUE constraint failed: events.external_event_id: SQLITE_CONSTRAINT" });
  const out = await recordInboundReply({ DB: db }, { from: P, text: "yes", ownerRef: "o1", externalId: SID });
  assert.deepEqual(out, { kind: "duplicate" });
});

if (failures) {
  console.error(`sender: ${failures} FAILED, ${passes} passed`);
  process.exit(1);
}
console.log(`sender: ${passes} checks passed`);
