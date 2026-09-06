/**
 * connections-store.test.ts — the four connections tables and the store over
 * them, driven against an in-process SQLite carrying the REAL
 * migration/d1/schema.sql (indexes, CHECKs and all) and, for every assertion
 * that can be, against the in-memory store as well.
 *
 *   node --experimental-strip-types migration/workers/test/connections-store.test.ts
 *
 * WHAT THESE PIN, and the concrete failure behind each:
 *
 *  1. THE TABLE SHAPE IS THE CONTRACT'S. This file PARSES
 *     spike/two-hands/src/connections/contract.ts — the fixed design — and
 *     compares the interfaces it declares against `pragma_table_info` on the
 *     real schema. The three deviations the spike found and reported
 *     (`token_handle` for `token`, `completed_at`, `alias` on signals) are
 *     named here with their reason; a FOURTH one, in either direction, is a
 *     red test rather than a comment nobody reads.
 *
 *  2. EVERY ACCESSOR FILTERS BY OWNER, and a mixed-owner answer is REFUSED.
 *     Filtering the stray row out hides the query that produced it; stamping
 *     our owner over it LAUNDERS another person's row into this person's
 *     account. During the spike three cross-owner paths were open and closed;
 *     these are the tests that keep them shut.
 *
 *  3. connect_links IS SINGLE USE UNDER CONCURRENCY. The redeem storm below
 *     runs through a D1 wrapper that inserts a real macrotask between every
 *     statement, so an implementation that reads the row, decides in
 *     JavaScript and writes it back — the double-redeem bug with extra steps —
 *     produces many winners and this file goes red.
 *
 *  4. THE 1101. A Worker that INSERTs a column the LIVE table lacks fails
 *     every write on that table, not the one column (live `events`,
 *     2026-09-05). The store asks pragma_table_info and either degrades or
 *     refuses by name.
 *
 *  5. THE CONTROLS. A guard that refuses everything is an outage, not a
 *     guard, so every tightening above has its twin here: the correctly
 *     scoped read still returns rows, the honest redeem still wins, the same
 *     owner's upsert still updates, the column that IS present still
 *     round-trips.
 *
 * MUTATIONS THIS FILE MUST GO RED ON (all run; see the agent's report):
 *   - `AND "used_at" IS NULL` dropped from the claim statement
 *   - claim rewritten as read-then-write
 *   - `WHERE "connections"."user_id" = excluded."user_id"` dropped from the
 *     putConnection upsert
 *   - `refuseMixedOwners` filtering instead of throwing
 *   - `WHERE "user_id" = ?1` dropped from the owner-scoped SELECT
 *   - `AND "user_id" = ?2` dropped from deleteConnection
 *   - the compare-and-set predicate dropped from the signal merge
 *   - `project()` ignoring the live column set
 *   - a column added to schema.sql that the contract does not declare
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { openTestD1, type TestDb } from "./sqlite-d1.ts";
import {
  createD1Store, createMemoryStore, ownerId, forgetLiveColumns,
  MixedOwnerRows, CrossOwnerWrite, ConnectionsSchemaMissing,
  SIGNAL_SOURCES, CONNECTION_STATUSES, NUDGE_STATES, NUDGE_TRIGGERS, NUDGE_CHANNELS,
  type ConnectionsStore, type StoredSignal, type StoredConnection,
  type StoredNudge, type StoredLink,
} from "../src/connections/store.ts";

let failures = 0;
let passes = 0;
async function check(what: string, fn: () => void | Promise<void>): Promise<void> {
  try { await fn(); passes++; }
  catch (err) { failures++; console.error("FAIL " + what + "\n     " + (err as Error).message); }
}

// Two real owner ids. `A` is the owner record for the person at this machine
// (research/2026-09-05-composio-connections.md); `B` is the stranger whose
// rows must never reach A, and whose rows A must never be able to move.
const A = ownerId("sxkotd1h02qb6gw");
const B = ownerId("b1c2d3e4f5g6h7i");

/** A 64-hex connect-link handle. Deterministic, so a failure names one row. */
function handle(seed: string): string {
  let h = "";
  for (let i = 0; h.length < 64; i++) {
    h += ((seed.charCodeAt(i % seed.length) * (i + 7)) % 256).toString(16).padStart(2, "0");
  }
  return h.slice(0, 64);
}

const NOW = 1_757_000_000_000; // 2025-09-04ish in epoch ms; any fixed instant.

function connection(over: Partial<StoredConnection> = {}): StoredConnection {
  return {
    user_id: A, toolkit: "gmail", connected_account_id: "ca_BNgvxQtJ703C", alias: "work",
    status: "connected", writes_enabled: false, last_used_at: null, ...over,
  } as StoredConnection;
}
function nudge(over: Partial<StoredNudge> = {}): StoredNudge {
  return {
    user_id: A, toolkit: "notion", state: "asked", level: 0, snooze_until: null,
    trigger: "in_task", sent_at: NOW, acted_at: null, channel: "sms", ...over,
  } as StoredNudge;
}
function link(over: Partial<StoredLink> = {}): StoredLink {
  return {
    token_handle: handle("one"), user_id: A, toolkit: "notion", alias: null,
    expires_at: NOW + 600_000, used_at: null, completed_at: null, ...over,
  } as StoredLink;
}

/** The merge signals.ts will own. Here it is the simplest honest one — add the
 *  arriving weight to whatever is already there — because this file is testing
 *  the WRITE, not the arithmetic. */
const addOne = (at: number) => (prior: StoredSignal | null) => ({
  weight: (prior?.weight ?? 0) + 1,
  last_seen_at: Math.max(prior?.last_seen_at ?? 0, at),
});

// ===========================================================================
// 1. THE TABLE SHAPE IS THE CONTRACT'S
// ===========================================================================
// The contract is FIXED and lives in the spike. This reads its source rather
// than importing it: the point is to compare two files that must agree, and an
// import would only prove that TypeScript compiled. If the spike tree ever
// moves, this test fails loudly on the read, which is the correct outcome —
// a shape test that silently skips is worse than no shape test.

const here = dirname(fileURLToPath(import.meta.url));
const CONTRACT = join(here, "..", "..", "..", "spike", "two-hands", "src", "connections", "contract.ts");

function contractSource(): string {
  return readFileSync(CONTRACT, "utf8");
}

/** The field names an `export interface X { ... }` declares, in order. */
function interfaceFields(src: string, name: string): string[] {
  const start = src.indexOf(`export interface ${name} {`);
  assert.notEqual(start, -1, `contract.ts no longer declares ${name}`);
  const open = src.indexOf("{", start);
  let depth = 0, end = open;
  for (let i = open; i < src.length; i++) {
    if (src[i] === "{") depth++;
    else if (src[i] === "}") { depth--; if (depth === 0) { end = i; break; } }
  }
  const body = src.slice(open + 1, end);
  const fields: string[] = [];
  for (const raw of body.split("\n")) {
    const line = raw.trim();
    if (line === "" || line.startsWith("*") || line.startsWith("/*") || line.startsWith("//")) continue;
    const m = /^([A-Za-z_][A-Za-z0-9_]*)\??\s*:/.exec(line);
    if (m) fields.push(m[1] as string);
  }
  return fields;
}

/** The string literals in a snippet of the contract, with comments stripped
 *  first — `NudgeTrigger` annotates each member with the moment it stands for
 *  (`user_named_it,  // they said "my Notion"`), and a quoted phrase inside a
 *  comment is not a member of the union. */
function stringLiterals(segment: string): string[] {
  const code = segment.replace(/\/\*[\s\S]*?\*\//g, " ").replace(/\/\/[^\n]*/g, " ");
  return [...code.matchAll(/"([^"]+)"/g)].map((x) => x[1] as string);
}

/** The string literals an `export type X = "a" | "b"` union declares. */
function unionMembers(src: string, name: string): string[] {
  const re = new RegExp(`export type ${name} =([\\s\\S]*?);`, "m");
  const m = re.exec(src);
  assert.ok(m, `contract.ts no longer declares type ${name}`);
  return stringLiterals((m as RegExpExecArray)[1] as string);
}

function tableColumns(t: TestDb, table: string): string[] {
  return t.query<{ name: string }>(`SELECT name FROM pragma_table_info(?)`, table).map((r) => r.name);
}

/**
 * The three deviations, declared. Anything else — a column the contract does
 * not declare, or a contract field with no column — is a failure.
 *
 * A "declared deviation" is not a loophole: each entry names the failure it
 * prevents, and adding a fourth means editing this file, which means somebody
 * had to write the reason down.
 */
const DEVIATIONS: Record<string, { drop?: string[]; add?: string[]; why: string }> = {
  AppUsageSignal: {
    add: ["alias"],
    why: "the contract's row cannot say WHICH of the owner's two accounts the evidence "
      + "was about, so work and personal would merge into one row and the ask could not "
      + "name the account (spike signals.ts StoredSignal, reported back as a contract problem)",
  },
  Connection: { why: "none — this table is exactly the contract" },
  ConnectNudge: { why: "none — this table is exactly the contract" },
  ConnectLink: {
    drop: ["token"], add: ["token_handle", "completed_at"],
    why: "token_handle replaces token because a raw single-use bearer token at rest means "
      + "one database read is a live connect link for every owner holding one; completed_at "
      + "is the exactly-once gate for the callback, without which a refresh of the done page "
      + "records the same connection twice",
  },
};

const TABLE_OF: Record<string, string> = {
  AppUsageSignal: "app_usage_signals",
  Connection: "connections",
  ConnectNudge: "connect_nudges",
  ConnectLink: "connect_links",
};

await check("every table's columns are exactly the contract's fields, plus only the declared deviations", () => {
  const t = openTestD1();
  const src = contractSource();
  for (const [iface, table] of Object.entries(TABLE_OF)) {
    const dev = DEVIATIONS[iface]!;
    const expected = new Set(interfaceFields(src, iface));
    for (const d of dev.drop ?? []) {
      assert.ok(expected.delete(d), `${iface} no longer declares ${d}; the deviation note is stale`);
    }
    for (const a of dev.add ?? []) expected.add(a);
    const actual = new Set(tableColumns(t, table));
    const missing = [...expected].filter((c) => !actual.has(c));
    const extra = [...actual].filter((c) => !expected.has(c));
    assert.deepEqual(missing, [], `${table} is missing contract fields: ${missing.join(", ")}`);
    assert.deepEqual(
      extra, [],
      `${table} has columns the contract does not declare and this file does not excuse: `
        + `${extra.join(", ")}. Either delete them or add a DEVIATIONS entry saying which `
        + "failure they prevent.",
    );
  }
  t.close();
});

await check("the store's closed sets are the contract's own unions, member for member", () => {
  const src = contractSource();
  // The store IMPORTS these as types (`AppUsageSignal["source"]` and friends),
  // so TypeScript already holds that half. What it cannot hold is the RUNTIME
  // list — `--experimental-strip-types` deletes every annotation before the
  // first line runs, so `SIGNAL_SOURCES` is a hand-written array and this is
  // the only thing standing between it and the contract. Without this check, a
  // sixth signal source added to the contract would type-check everywhere and
  // be silently unwritable, and nobody would find out until an owner's
  // evidence stopped counting.
  //
  // `source` is declared inline inside AppUsageSignal, the rest as named types.
  const sourceLine = /source:\s*([^;]+);/.exec(src);
  assert.ok(sourceLine, "contract.ts no longer declares AppUsageSignal.source");
  const sources = stringLiterals((sourceLine as RegExpExecArray)[1] as string);
  assert.deepEqual([...SIGNAL_SOURCES].sort(), sources.sort(), "SIGNAL_SOURCES drifted from the contract");

  const statusLine = /status:\s*([^;]+);/.exec(src);
  assert.ok(statusLine, "contract.ts no longer declares Connection.status");
  const statuses = stringLiterals((statusLine as RegExpExecArray)[1] as string);
  assert.deepEqual([...CONNECTION_STATUSES].sort(), statuses.sort(), "CONNECTION_STATUSES drifted");

  assert.deepEqual([...NUDGE_STATES].sort(), unionMembers(src, "NudgeState").sort(), "NUDGE_STATES drifted");
  assert.deepEqual([...NUDGE_TRIGGERS].sort(), unionMembers(src, "NudgeTrigger").sort(), "NUDGE_TRIGGERS drifted");

  const channelLine = /channel:\s*([^;]+);/.exec(src);
  assert.ok(channelLine, "contract.ts no longer declares ConnectNudge.channel");
  const channels = stringLiterals((channelLine as RegExpExecArray)[1] as string);
  assert.deepEqual([...NUDGE_CHANNELS].sort(), channels.sort(), "NUDGE_CHANNELS drifted");
});

await check("the store's owner-id rule is the contract's own, character for character", () => {
  const src = contractSource();
  assert.ok(
    src.includes("/^[a-z0-9]{15}$/"),
    "contract.ts changed the owner id shape; store.ts's copy of it is now wrong, and the "
      + "wrong-person failure is exactly what that regex is standing in front of",
  );
  // And the copy in the store behaves the same way, at run time, where the
  // brand has already been erased.
  assert.throws(() => ownerId("omar"), /not an owner id/,
    "a NAME must never become an owner id — one operator's mailbox serving everybody is "
      + "how this feature already went wrong once");
  assert.throws(() => ownerId("jose@anticipy.ai"), /not an owner id/, "an EMAIL is not an id either");
  assert.throws(() => ownerId("SXKOTD1H02QB6GW"), /not an owner id/, "ids are lowercase");
  assert.equal(ownerId("sxkotd1h02qb6gw"), "sxkotd1h02qb6gw", "CONTROL: a real id still passes");
});

// ===========================================================================
// 2. THE DATABASE IS THE VALIDATOR — these tables never had PocketBase's Go.
// ===========================================================================
// Every closed enum in the contract is a CHECK in schema.sql. These insert
// straight into SQLite, NOT through the store, so what answers is the
// database. A CHECK that only TypeScript enforces is a CHECK that stops
// nothing the day a second writer appears.

function refuses(t: TestDb, sql: string): boolean {
  try { t.exec(sql); return false; } catch { return true; }
}

await check("the database itself refuses a value outside a contract enum, and accepts one inside it", () => {
  const t = openTestD1();
  const bad = [
    ["a sixth signal source",
     `INSERT INTO app_usage_signals (user_id,toolkit,source,alias,weight,last_seen_at)
      VALUES ('${A}','notion','vibes','',1,1)`],
    ["a fourth connection status",
     `INSERT INTO connections (connected_account_id,user_id,toolkit,alias,status,writes_enabled)
      VALUES ('ca_1','${A}','gmail','','maybe',0)`],
    ["a sixth nudge state",
     `INSERT INTO connect_nudges (user_id,toolkit,state,level) VALUES ('${A}','notion','pondering',0)`],
    ["a fourth decline level — LEVEL_THRESHOLD is indexed by 0..3 and a 4 would restart the asking",
     `INSERT INTO connect_nudges (user_id,toolkit,state,level) VALUES ('${A}','notion','declined',4)`],
    ["a trigger that is not a real moment",
     `INSERT INTO connect_nudges (user_id,toolkit,state,level,trigger) VALUES ('${A}','notion','asked',0,'vibes')`],
    ["a third channel",
     `INSERT INTO connect_nudges (user_id,toolkit,state,level,channel) VALUES ('${A}','notion','asked',0,'fax')`],
    ["a third account alias",
     `INSERT INTO connections (connected_account_id,user_id,toolkit,alias,status,writes_enabled)
      VALUES ('ca_2','${A}','gmail','side','connected',0)`],
    ["a NAME where an owner id belongs",
     `INSERT INTO connect_nudges (user_id,toolkit,state,level) VALUES ('omar','notion','asked',0)`],
    ["a RAW 43-character connect token where the sha256 handle belongs",
     `INSERT INTO connect_links (token_handle,user_id,toolkit,alias,expires_at)
      VALUES ('${"a".repeat(43)}','${A}','notion','',1)`],
    ["a negative signal weight — evidence must never SUBTRACT evidence",
     `INSERT INTO app_usage_signals (user_id,toolkit,source,alias,weight,last_seen_at)
      VALUES ('${A}','notion','said','',-1,1)`],
  ] as const;
  for (const [what, sql] of bad) {
    assert.ok(refuses(t, sql), `the database ACCEPTED ${what}`);
  }

  // THE CONTROL. Every one of those tables still takes a good row — a schema
  // that refuses everything is an outage with a CHECK constraint.
  t.exec(`INSERT INTO app_usage_signals (user_id,toolkit,source,alias,weight,last_seen_at)
          VALUES ('${A}','notion','said','work',1,1)`);
  t.exec(`INSERT INTO connections (connected_account_id,user_id,toolkit,alias,status,writes_enabled)
          VALUES ('ca_ok','${A}','gmail','work','connected',0)`);
  t.exec(`INSERT INTO connect_nudges (user_id,toolkit,state,level,trigger,channel)
          VALUES ('${A}','notion','declined',3,'onboarding','ios')`);
  t.exec(`INSERT INTO connect_links (token_handle,user_id,toolkit,alias,expires_at)
          VALUES ('${handle("ok")}','${A}','notion','work',1)`);
  assert.equal(t.query<{ n: number }>(`SELECT COUNT(*) AS n FROM connect_links`)[0]!.n, 1);
  t.close();
});

await check("writes_enabled defaults to OFF, so a column added later cannot opt anyone into writes", () => {
  const t = openTestD1();
  t.exec(`INSERT INTO connections (connected_account_id,user_id,toolkit,status)
          VALUES ('ca_default','${A}','gmail','connected')`);
  const row = t.query<{ writes_enabled: number }>(
    `SELECT writes_enabled FROM connections WHERE connected_account_id='ca_default'`)[0]!;
  assert.equal(row.writes_enabled, 0,
    "THE WRITE OPT-IN must be off by default: a column added to a live table backfills with its "
      + "default, and a default of 1 opts every existing owner into changes they never agreed to");
  t.close();
});

// ===========================================================================
// 3. THE CONFORMANCE SUITE — the same assertions against BOTH stores.
// ===========================================================================
// A fake that accepts what D1 refuses is a test suite that passes on a
// product that does not work. So the owner-scoping half runs twice: once
// against the in-memory store the modules above will unit-test with, once
// against the real schema in SQLite.

async function conformance(kind: string, make: () => { store: ConnectionsStore; close: () => void }) {
  const label = (s: string) => `[${kind}] ${s}`;

  await check(label("CONTROL — a correctly scoped read returns this owner's rows, all of them"), async () => {
    const { store, close } = make();
    await store.recordSignal({ user_id: A, toolkit: "notion", source: "observer" }, addOne(NOW));
    await store.recordSignal({ user_id: A, toolkit: "slack", source: "said" }, addOne(NOW));
    await store.putConnection(connection());
    await store.putNudge(nudge());
    await store.put(link());

    const signals = await store.signalsForOwner(A);
    assert.equal(signals.length, 2, "both of this owner's signal rows must come back");
    assert.deepEqual(signals.map((s) => s.toolkit).sort(), ["notion", "slack"]);
    assert.equal((await store.connectionsForOwner(A)).length, 1);
    assert.equal((await store.nudgesForOwner(A)).length, 1);
    assert.equal((await store.linksForOwner(A)).length, 1);
    assert.equal((await store.readNudge(A, "notion"))?.state, "asked");
    assert.equal((await store.readConnection(A, "ca_BNgvxQtJ703C"))?.toolkit, "gmail");
    assert.equal((await store.readSignal({ user_id: A, toolkit: "slack", source: "said" }))?.weight, 1);
    close();
  });

  await check(label("every accessor is scoped by owner: B's rows never reach A, and A's never reach B"), async () => {
    const { store, close } = make();
    // B lives here too, with the SAME toolkit and a colliding-looking shape.
    await store.recordSignal({ user_id: B, toolkit: "notion", source: "observer" }, addOne(NOW));
    await store.putConnection(connection({ user_id: B, connected_account_id: "ca_theirs" }));
    await store.putNudge(nudge({ user_id: B }));
    await store.put(link({ user_id: B, token_handle: handle("theirs") }));

    assert.deepEqual(await store.signalsForOwner(A), [], "A has no signals and must be told so");
    assert.deepEqual(await store.connectionsForOwner(A), []);
    assert.deepEqual(await store.nudgesForOwner(A), []);
    assert.deepEqual(await store.linksForOwner(A), []);
    assert.equal(await store.readNudge(A, "notion"), null,
      "B's nudge for the same app must not answer A's read");
    assert.equal(await store.readSignal({ user_id: A, toolkit: "notion", source: "observer" }), null);
    assert.equal(await store.readConnection(A, "ca_theirs"), null,
      "knowing the vendor's account id must not be enough to read somebody else's connection");

    // And the same in the other direction, so this is scoping and not an
    // accident of insertion order.
    assert.equal((await store.connectionsForOwner(B)).length, 1);
    assert.equal((await store.nudgesForOwner(B)).length, 1);
    close();
  });

  await check(label("A cannot DELETE B's connection, and B's row survives the attempt"), async () => {
    const { store, close } = make();
    await store.putConnection(connection({ user_id: B, connected_account_id: "ca_theirs" }));
    assert.equal(await store.deleteConnection(A, "ca_theirs"), false,
      "a delete by vendor id alone would let one owner disconnect another's mailbox by guessing an id");
    assert.equal((await store.connectionsForOwner(B)).length, 1, "B's connection was deleted by A");
    // CONTROL: B can still delete it, so this is scoping and not a broken delete.
    assert.equal(await store.deleteConnection(B, "ca_theirs"), true);
    assert.equal((await store.connectionsForOwner(B)).length, 0);
    close();
  });

  await check(label("putConnection REFUSES to re-bind a connected account that belongs to somebody else"), async () => {
    const { store, close } = make();
    await store.putConnection(connection({ user_id: B, connected_account_id: "ca_shared" }));
    await assert.rejects(
      () => store.putConnection(connection({ user_id: A, connected_account_id: "ca_shared" })),
      (err: unknown) => err instanceof CrossOwnerWrite,
      "the vendor's connected_account_id is unique ACROSS owners, so a plain upsert on it "
        + "re-binds a stranger's account to this owner in one statement and logs success",
    );
    const theirs = await store.readConnection(B, "ca_shared");
    assert.equal(theirs?.user_id, B, "B's connection was re-bound to A");
    // CONTROL: the SAME owner's upsert still updates. A guard that refuses
    // every second write is an outage.
    await store.putConnection(connection({
      user_id: B, connected_account_id: "ca_shared", writes_enabled: true, status: "needs_reconnect",
    }));
    const after = await store.readConnection(B, "ca_shared");
    assert.equal(after?.writes_enabled, true, "the owner's own update did not apply");
    assert.equal(after?.status, "needs_reconnect");
    close();
  });

  await check(label("a connect link is single use: one claim wins, later claims lose and say so"), async () => {
    const { store, close } = make();
    const h = handle("single");
    await store.put(link({ token_handle: h }));
    const first = await store.claim(h, NOW);
    assert.equal(first.won, true, "CONTROL: the honest first redeem must win");
    assert.equal(first.row?.used_at, NOW);
    const second = await store.claim(h, NOW + 1);
    assert.equal(second.won, false, "a token redeemed twice is a link that is not single use");
    assert.equal(second.row?.used_at, NOW, "the loser must not move the winner's stamp");
    close();
  });

  await check(label("the callback lease is exactly-once, and can be handed back only by its holder"), async () => {
    const { store, close } = make();
    const h = handle("lease");
    await store.put(link({ token_handle: h }));
    assert.equal((await store.complete(h, NOW)).won, true, "CONTROL: the first callback takes the lease");
    assert.equal((await store.complete(h, NOW + 1)).won, false,
      "a refresh of the done page would record the same connection twice");

    // A stale caller holding the WRONG completion stamp may not re-open the
    // window: doing so would clear the completion of a connection another
    // callback already wrote, and the next refresh would write it twice.
    assert.equal((await store.release(h, NOW + 999)).won, false);
    assert.equal((await store.read(h))?.completed_at, NOW, "a stale release cleared a live lease");

    // CONTROL: the holder CAN hand it back, which is the whole reason release
    // exists — without it one failed write leaves the token completed with no
    // connection row anywhere, forever, and Composio publishes no success
    // webhook to tell anyone.
    assert.equal((await store.release(h, NOW)).won, true);
    assert.equal((await store.read(h))?.completed_at, null);
    assert.equal((await store.complete(h, NOW + 5)).won, true, "the retry after a release must succeed");
    close();
  });

  await check(label("a token that was minted twice is refused, never overwritten"), async () => {
    const { store, close } = make();
    const h = handle("dupe");
    await store.put(link({ token_handle: h, user_id: A }));
    await assert.rejects(
      () => store.put(link({ token_handle: h, user_id: B, toolkit: "slack" })),
      "an overwrite would re-bind a link somebody is already holding to a different owner",
    );
    const row = await store.read(h);
    assert.equal(row?.user_id, A);
    assert.equal(row?.toolkit, "notion");
    close();
  });

  await check(label("claim and complete on a handle that does not exist lose quietly"), async () => {
    const { store, close } = make();
    const missing = await store.claim(handle("ghost"), NOW);
    assert.equal(missing.won, false);
    assert.equal(missing.row, null, "no row means no row; inventing one is inventing a link");
    close();
  });

  await check(label("a name or an email is refused wherever an owner id belongs"), async () => {
    const { store, close } = make();
    for (const notAnId of ["omar", "jose@anticipy.ai", "", "sxkotd1h02qb6g"]) {
      await assert.rejects(() => store.signalsForOwner(notAnId), /not an owner id/,
        `${JSON.stringify(notAnId)} reached a query as an owner id`);
      await assert.rejects(() => store.connectionsForOwner(notAnId), /not an owner id/);
      await assert.rejects(() => store.nudgesForOwner(notAnId), /not an owner id/);
      await assert.rejects(() => store.linksForOwner(notAnId), /not an owner id/);
      await assert.rejects(() => store.deleteConnection(notAnId, "ca_1"), /not an owner id/);
    }
    close();
  });

  await check(label("a value outside a contract enum never reaches a row"), async () => {
    const { store, close } = make();
    await assert.rejects(
      () => store.recordSignal({ user_id: A, toolkit: "notion", source: "vibes" as never }, addOne(NOW)),
      /not a signal source/);
    await assert.rejects(
      () => store.putConnection(connection({ status: "maybe" as never })), /not a connection status/);
    await assert.rejects(
      () => store.putNudge(nudge({ state: "pondering" as never })), /not a nudge state/);
    await assert.rejects(
      () => store.putNudge(nudge({ level: 4 as never })), /nudge level/);
    await assert.rejects(
      () => store.putConnection(connection({ alias: "side" as never })), /not an account alias/);
    await assert.rejects(
      () => store.put(link({ token_handle: "a".repeat(43) })), /connect-link handle/,
      "the raw 43-character token must be impossible to store");
    await assert.rejects(
      () => store.putConnection(connection({ writes_enabled: "true" as never })), /writes_enabled/,
      '"false" is truthy in JavaScript, and this field decides whether Anticipy may act');
    close();
  });

  await check(label("evidence accumulates rather than overwrites, and every row round-trips"), async () => {
    const { store, close } = make();
    const key = { user_id: A, toolkit: "notion", source: "observer" as const };
    await store.recordSignal(key, addOne(NOW));
    await store.recordSignal(key, addOne(NOW + 1000));
    const row = await store.readSignal(key);
    assert.equal(row?.weight, 2, "the second observation did not add");
    assert.equal(row?.last_seen_at, NOW + 1000);

    // Work and personal are two piles of evidence, not one: alias is part of
    // the key. Folding them would be this store deciding which of the owner's
    // two accounts somebody meant.
    await store.recordSignal({ ...key, alias: "work" }, addOne(NOW));
    assert.equal((await store.readSignal(key))?.weight, 2, "the aliased row merged into the unaliased one");
    assert.equal((await store.readSignal({ ...key, alias: "work" }))?.weight, 1);
    assert.equal((await store.signalsForOwner(A)).length, 2);
    close();
  });

  await check(label("every nullable the contract declares survives a round trip as null"), async () => {
    const { store, close } = make();
    await store.putNudge(nudge({
      state: "never_asked", level: 0, snooze_until: null, trigger: null,
      sent_at: null, acted_at: null, channel: null,
    }));
    const back = await store.readNudge(A, "notion");
    assert.equal(back?.snooze_until, null);
    assert.equal(back?.trigger, null);
    assert.equal(back?.sent_at, null);
    // acted_at null is a FACT and not a missing value: a decline by SILENCE
    // must not stamp an action nobody took, and the spec's timers are tuned
    // from this column.
    assert.equal(back?.acted_at, null);
    assert.equal(back?.channel, null);
    await store.putConnection(connection({ alias: null, last_used_at: null }));
    const conn = await store.readConnection(A, "ca_BNgvxQtJ703C");
    assert.equal(conn?.alias, null, "'' must read back as the contract's null, not as an empty alias");
    assert.equal(conn?.last_used_at, null);

    // CONTROL: the same fields carry real values when there are real values.
    await store.putNudge(nudge({ snooze_until: NOW + 1, trigger: "onboarding", acted_at: NOW, channel: "ios" }));
    const filled = await store.readNudge(A, "notion");
    assert.equal(filled?.snooze_until, NOW + 1);
    assert.equal(filled?.trigger, "onboarding");
    assert.equal(filled?.acted_at, NOW);
    assert.equal(filled?.channel, "ios");
    close();
  });

  await check(label("a row handed back is a copy: mutating it does not edit the database"), async () => {
    const { store, close } = make();
    const h = handle("copy");
    await store.put(link({ token_handle: h }));
    const row = (await store.read(h))!;
    row.used_at = NOW;                       // the field the whole module refuses to decide elsewhere
    assert.equal((await store.read(h))?.used_at, null, "a caller edited the store by mutating a row");
    close();
  });
}

await conformance("memory", () => ({ store: createMemoryStore(), close: () => {} }));
await conformance("d1", () => {
  const t = openTestD1();
  return { store: createD1Store({ DB: t.db }), close: () => t.close() };
});

// ===========================================================================
// 4. THE MIXED-OWNER REFUSAL — refused, never filtered, never laundered.
// ===========================================================================
// Reached by breaking the guard the way it actually breaks: the WHERE is
// there, and the answer still carries a stranger. In production that is a
// dropped clause, a cache keyed one field too loosely, or a join that
// multiplied. Here it is a view that lies, which is the same shape from the
// store's side and the only way to test a defence without shipping the defect.

/**
 * A D1 whose every `"user_id" = ?N` predicate has been neutralised — the
 * dropped WHERE clause, made real, without editing a shipped statement. In
 * production this is a clause somebody deleted, a cache keyed one field too
 * loosely, or a join that multiplied; from the store's side all three look
 * the same, and this is the shape the refusal has to survive.
 */
function ownerBlindD1(db: D1Database): D1Database {
  return {
    prepare(sql: string) {
      return (db as D1Database).prepare(sql.replace(/"user_id" = (\?\d+)/g, "$1 = $1"));
    },
  } as unknown as D1Database;
}

await check("EVERY read accessor refuses when its owner clause stops biting", async () => {
  const t = openTestD1();
  const store = createD1Store({ DB: t.db });
  // B lives here, on the same apps, with the same shapes.
  await store.putConnection(connection({ user_id: B, connected_account_id: "ca_theirs" }));
  await store.putNudge(nudge({ user_id: B }));
  await store.put(link({ user_id: B, token_handle: handle("theirs") }));
  await store.recordSignal({ user_id: B, toolkit: "notion", source: "observer" }, addOne(NOW));

  const blind = createD1Store({ DB: ownerBlindD1(t.db) });
  const reads: [string, () => Promise<unknown>][] = [
    ["connectionsForOwner", () => blind.connectionsForOwner(A)],
    ["nudgesForOwner", () => blind.nudgesForOwner(A)],
    ["linksForOwner", () => blind.linksForOwner(A)],
    ["signalsForOwner", () => blind.signalsForOwner(A)],
    ["readConnection", () => blind.readConnection(A, "ca_theirs")],
    ["readNudge", () => blind.readNudge(A, "notion")],
    ["readSignal", () => blind.readSignal({ user_id: A, toolkit: "notion", source: "observer" })],
    // recordSignal re-reads through readSignal before it merges, so a blind
    // query cannot make this owner's evidence land on a stranger's row.
    ["recordSignal", () => blind.recordSignal({ user_id: A, toolkit: "notion", source: "observer" }, addOne(NOW))],
  ];
  for (const [name, call] of reads) {
    const err = await call().then(() => null, (e: Error) => e);
    assert.ok(
      err instanceof MixedOwnerRows,
      `${name} handed the caller a stranger's row instead of refusing (got ${err?.name ?? "a result"})`,
    );
    // REFUSED, not filtered and not laundered. Filtering hides the broken
    // query so it ships; stamping our owner over the stray row LAUNDERS
    // another person's row into this person's account, which is the
    // wrong-person failure arriving through the code meant to prevent it.
    assert.match((err as Error).message, /refusing rather than filtering/);
    assert.deepEqual((err as MixedOwnerRows).found, [B], `${name} named the wrong stray owner`);
  }
  // deleteConnection is not in that list because it has no answer to refuse —
  // its guard is the `AND "user_id" = ?2` in the DELETE itself, pinned by the
  // "A cannot DELETE B's connection" check above and by mutation M6.

  // THE CONTROL, on the very same database: the intact store still answers,
  // and answers with rows. A guard that refuses everything is an outage.
  await store.putConnection(connection({ user_id: A, connected_account_id: "ca_mine" }));
  await store.putNudge(nudge({ user_id: A, toolkit: "slack" }));
  await store.put(link({ user_id: A, token_handle: handle("mine") }));
  await store.recordSignal({ user_id: A, toolkit: "slack", source: "said" }, addOne(NOW));
  assert.deepEqual((await store.connectionsForOwner(A)).map((r) => r.connected_account_id), ["ca_mine"]);
  assert.deepEqual((await store.nudgesForOwner(A)).map((r) => r.toolkit), ["slack"]);
  assert.deepEqual((await store.linksForOwner(A)).map((r) => r.token_handle), [handle("mine")]);
  assert.deepEqual((await store.signalsForOwner(A)).map((r) => r.toolkit), ["slack"]);
  assert.equal((await store.readNudge(A, "slack"))?.state, "asked");
  t.close();
});

await check("the memory store refuses the same shape, so the fake cannot be laxer than D1", async () => {
  const store = createMemoryStore();
  await store.putConnection(connection({ user_id: A, connected_account_id: "ca_mine" }));
  const rows = await store.connectionsForOwner(A);
  assert.equal(rows.length, 1, "CONTROL: the scoped read works");
  // The refusal helper is shared by both stores and is exercised above through
  // D1; here it is proved reachable from the memory path by handing it a row
  // that is not this owner's through the only door that takes one.
  await assert.rejects(
    () => store.putConnection(connection({ user_id: B, connected_account_id: "ca_mine" })),
    (err: unknown) => err instanceof CrossOwnerWrite);
});

// ===========================================================================
// 5. SINGLE USE UNDER CONCURRENCY
// ===========================================================================

/**
 * A D1 that puts a REAL macrotask between every statement, so any
 * read-then-write in the store interleaves with its rivals. Against the
 * shipped single-statement UPDATE this changes nothing — SQLite decides — and
 * that is the point of the test: it can only go red for the wrong reason.
 */
function slowD1(db: D1Database): D1Database {
  const tick = () => new Promise<void>((r) => setTimeout(r, 0));
  type Stmt = { bind(...a: unknown[]): Stmt; first(): Promise<unknown>; all(): Promise<unknown>; run(): Promise<unknown> };
  const wrap = (s: Stmt): Stmt => ({
    bind: (...a: unknown[]) => wrap(s.bind(...a)),
    async first() { await tick(); const r = await s.first(); await tick(); return r; },
    async all() { await tick(); const r = await s.all(); await tick(); return r; },
    async run() { await tick(); const r = await s.run(); await tick(); return r; },
  });
  return { prepare: (sql: string) => wrap((db as unknown as { prepare(s: string): Stmt }).prepare(sql)) } as unknown as D1Database;
}

await check("25 simultaneous redeems of one link: exactly ONE wins", async () => {
  const t = openTestD1();
  const store = createD1Store({ DB: slowD1(t.db) });
  const h = handle("storm");
  await store.put(link({ token_handle: h }));

  const results = await Promise.all(
    Array.from({ length: 25 }, (_, i) => store.claim(h, NOW + i)),
  );
  const winners = results.filter((r) => r.won);
  assert.equal(winners.length, 1,
    `${winners.length} redeems won the same single-use link. A link that can be redeemed twice `
      + "connects a second account, or connects somebody else's.");

  // The database agrees, and the stamp is the winner's.
  const rows = t.query<{ used_at: number }>(`SELECT used_at FROM connect_links WHERE token_handle = ?`, h);
  assert.equal(rows.length, 1);
  assert.equal(rows[0]!.used_at, winners[0]!.row!.used_at);
  assert.notEqual(rows[0]!.used_at, null);
  t.close();
});

await check("25 simultaneous callbacks on one link: exactly ONE takes the lease", async () => {
  const t = openTestD1();
  const store = createD1Store({ DB: slowD1(t.db) });
  const h = handle("callback");
  await store.put(link({ token_handle: h }));
  const results = await Promise.all(
    Array.from({ length: 25 }, (_, i) => store.complete(h, NOW + i)),
  );
  assert.equal(results.filter((r) => r.won).length, 1,
    "two callbacks holding the lease means the same connection is written twice");
  t.close();
});

await check("CONTROL — under the same interleaving, an uncontested redeem still wins", async () => {
  const t = openTestD1();
  const store = createD1Store({ DB: slowD1(t.db) });
  const h = handle("alone");
  await store.put(link({ token_handle: h }));
  assert.equal((await store.claim(h, NOW)).won, true,
    "a single-use gate that refuses the FIRST redeem is an outage, not a gate");
  t.close();
});

await check("simultaneous evidence for one app does not lose a signal", async () => {
  const t = openTestD1();
  const store = createD1Store({ DB: slowD1(t.db) });
  const key = { user_id: A, toolkit: "notion", source: "observer" as const };
  // Four observer traces landing together. Read-then-write loses three of
  // them: all four read weight 0, all four write 1.
  await Promise.all(Array.from({ length: 4 }, (_, i) => store.recordSignal(key, addOne(NOW + i))));
  const row = await store.readSignal(key);
  assert.equal(row?.weight, 4,
    `four observations summed to ${row?.weight}. A lost update here is evidence quietly `
      + "thrown away on the write path that runs most often");
  t.close();
});

// ===========================================================================
// 6. THE 1101 — the live table is the authority, not schema.sql.
// ===========================================================================

await check("a live table missing a SAFETY column makes the store refuse BY NAME, not 1101 on every write", async () => {
  const t = openTestD1();
  // The live table is an older revision: no exactly-once gate.
  t.exec(`ALTER TABLE "connect_links" DROP COLUMN "completed_at"`);
  const store = createD1Store({ DB: t.db });
  const err = await store.put(link()).then(() => null, (e: Error) => e);
  assert.ok(err instanceof ConnectionsSchemaMissing,
    `expected a named refusal naming the migration, got ${err?.name}: ${err?.message}`);
  assert.match(err.message, /completed_at/);
  assert.match(err.message, /schema\.sql/, "the refusal must say what to run");
  assert.deepEqual((err as ConnectionsSchemaMissing).missing, ["completed_at"]);
  t.close();
});

await check("the global ask budget's column is treated as safety, not as tuning", async () => {
  const t = openTestD1();
  // "One ask per owner per 7 days across ALL apps" is a MAX(sent_at) over this
  // owner's nudge rows. A sent_at that silently does not persist makes that
  // budget blind, and somebody who just ran three browser tasks gets three
  // connect texts — the spam the spec forbids, arriving through a column that
  // looked like a log field.
  t.exec(`ALTER TABLE "connect_nudges" DROP COLUMN "sent_at"`);
  const store = createD1Store({ DB: t.db });
  const err = await store.putNudge(nudge()).then(() => null, (e: Error) => e);
  assert.ok(err instanceof ConnectionsSchemaMissing, `got ${err?.name}`);
  assert.deepEqual((err as ConnectionsSchemaMissing).missing, ["sent_at"]);
  t.close();
});

await check("a live table missing an OPTIONAL column degrades instead of failing every write", async () => {
  const t = openTestD1();
  // `channel` is tuning: which way the ask went out. Losing it costs a log
  // line, so the write must still land — the 1101 is the failure to avoid.
  t.exec(`ALTER TABLE "connect_nudges" DROP COLUMN "channel"`);
  const store = createD1Store({ DB: t.db });
  await store.putNudge(nudge({ channel: "sms" }));
  const back = await store.readNudge(A, "notion");
  assert.equal(back?.state, "asked", "the nudge did not persist at all");
  assert.equal(back?.channel, null, "a column the table lacks must read back as the documented null");
  t.close();
});

await check("an alias that the live table cannot hold is REFUSED, because merging two accounts is not a degradation", async () => {
  const t = openTestD1();
  t.exec(`ALTER TABLE "connections" DROP COLUMN "alias"`);
  const store = createD1Store({ DB: t.db });
  await assert.rejects(
    () => store.putConnection(connection({ alias: "work" })),
    (err: unknown) => err instanceof ConnectionsSchemaMissing,
    "writing 'work' into a table that cannot store it merges the owner's two accounts, and the "
      + "next sentence out of this product is 'connect your work Gmail' pointing at the personal one",
  );
  // CONTROL: with no alias to lose, the same write goes through. A guard that
  // refuses every write to an older table is an outage.
  await store.putConnection(connection({ alias: null }));
  assert.equal((await store.readConnection(A, "ca_BNgvxQtJ703C"))?.alias, null);
  t.close();
});

await check("a table that does not exist yet refuses by name and is not cached as broken", async () => {
  const t = openTestD1();
  t.exec(`DROP TABLE "connect_nudges"`);
  const store = createD1Store({ DB: t.db });
  const err = await store.putNudge(nudge()).then(() => null, (e: Error) => e);
  assert.ok(err instanceof ConnectionsSchemaMissing, `got ${err?.name}`);
  assert.match(err.message, /wrangler d1 execute/, "the refusal must carry the command to run");

  // AND THE MIGRATION TAKES EFFECT WITHOUT A RESTART. An empty pragma result
  // cached as "this table has no columns" would make the store refuse a
  // database that is now correct, and the fix would be "restart every
  // isolate" — which on Cloudflare means waiting.
  t.exec(`CREATE TABLE "connect_nudges" (
            "user_id" TEXT NOT NULL, "toolkit" TEXT NOT NULL, "state" TEXT NOT NULL,
            "level" INTEGER NOT NULL DEFAULT 0, "snooze_until" REAL NULL, "trigger" TEXT NULL,
            "sent_at" REAL NULL, "acted_at" REAL NULL, "channel" TEXT NULL,
            PRIMARY KEY ("user_id","toolkit"))`);
  await store.putNudge(nudge());
  assert.equal((await store.readNudge(A, "notion"))?.state, "asked");
  t.close();
});

await check("CONTROL — against the real schema, nothing refuses and every table writes", async () => {
  const t = openTestD1();
  const store = createD1Store({ DB: t.db });
  await store.recordSignal({ user_id: A, toolkit: "notion", source: "said", alias: "work" }, addOne(NOW));
  await store.putConnection(connection({ alias: "personal", writes_enabled: true, last_used_at: NOW }));
  await store.putNudge(nudge({ channel: "ios", trigger: "laptop_closed", snooze_until: NOW + 1 }));
  await store.put(link({ alias: "work" }));
  assert.equal((await store.signalsForOwner(A))[0]!.alias, "work");
  assert.equal((await store.connectionsForOwner(A))[0]!.writes_enabled, true);
  assert.equal((await store.nudgesForOwner(A))[0]!.trigger, "laptop_closed");
  assert.equal((await store.linksForOwner(A))[0]!.alias, "work");
  t.close();
});

// ===========================================================================
// 7. THE LOOPS TERMINATE, AND THE STALE CACHE HAS AN ESCAPE HATCH.
// ===========================================================================

await check("a signal merge that keeps losing gives up loudly instead of spinning forever", async () => {
  const t = openTestD1();
  // A D1 whose UPDATEs never take: every compare-and-set reports 0 changes,
  // which is what "somebody else won again" looks like from inside the loop.
  const neverWins = {
    prepare(sql: string) {
      const stmt = (t.db as D1Database).prepare(sql);
      if (!/^UPDATE "app_usage_signals"/.test(sql)) return stmt;
      return {
        bind: (...a: unknown[]) => ({ async run() { await stmt.bind(...a).run(); return { meta: { changes: 0 } }; } }),
      };
    },
  } as unknown as D1Database;
  const store = createD1Store({ DB: neverWins });
  const key = { user_id: A, toolkit: "notion", source: "observer" as const };
  await store.recordSignal(key, addOne(NOW));            // the INSERT leg still works
  const err = await store.recordSignal(key, addOne(NOW + 1)).then(() => null, (e: Error) => e);
  assert.equal(err?.name, "SignalContention",
    "an unbounded retry loop inside a Worker is worse than an error: it holds a D1 connection "
      + "until the request is killed, and nothing says why");
  assert.match((err as Error).message, /Nothing was written/,
    "the message must say the evidence was lost and not corrupted");
  t.close();
});

await check("the live-column answer is cached per DATABASE, and a migration can clear it", async () => {
  const t = openTestD1();
  t.exec(`ALTER TABLE "connect_nudges" DROP COLUMN "channel"`);
  const store = createD1Store({ DB: t.db });
  await store.putNudge(nudge({ channel: "sms" }));
  assert.equal((await store.readNudge(A, "notion"))?.channel, null, "degraded, as it should");

  // Migrate underneath a warm isolate. The cache is now stale, exactly as
  // records.ts's is — that is the known cost of asking pragma_table_info once.
  t.exec(`ALTER TABLE "connect_nudges" ADD COLUMN "channel" TEXT NULL`);
  await store.putNudge(nudge({ channel: "sms" }));
  assert.equal((await store.readNudge(A, "notion"))?.channel, null,
    "the point of this check is that a warm isolate KEEPS degrading; if this ever passes as "
      + "'sms' the cache changed and forgetLiveColumns is dead code");

  // THE ESCAPE HATCH, which is why forgetLiveColumns is exported: after the
  // migration runs, the operator does not have to wait for every isolate on
  // Cloudflare to recycle.
  forgetLiveColumns({ DB: t.db });
  await store.putNudge(nudge({ channel: "sms" }));
  assert.equal((await store.readNudge(A, "notion"))?.channel, "sms");
  t.close();
});

await check("two databases in one isolate do not answer for each other's shape", async () => {
  const migrated = openTestD1();
  const older = openTestD1();
  older.exec(`ALTER TABLE "connect_nudges" DROP COLUMN "channel"`);
  const a = createD1Store({ DB: migrated.db });
  const b = createD1Store({ DB: older.db });
  await b.putNudge(nudge({ channel: "sms" }));          // warms the cache for the OLD shape
  await a.putNudge(nudge({ channel: "sms" }));
  assert.equal((await a.readNudge(A, "notion"))?.channel, "sms",
    "a column cache keyed by table name alone answers for the wrong database — free correctness, "
      + "so it is a WeakMap on the D1 handle instead");
  migrated.close(); older.close();
});

console.log(`connections-store: ${passes} checks passed, ${failures} failed`);
if (failures) process.exit(1);
